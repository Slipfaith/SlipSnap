"""Поток автоматического скролл-захвата окна."""

from __future__ import annotations

import random
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

try:
    import win32api
    import win32con
    import win32gui
    import win32ui
except Exception:  # pragma: no cover - защита окружений без WinAPI
    win32api = None
    win32con = None
    win32gui = None
    win32ui = None

try:
    import pythoncom
    from comtypes import client
    from comtypes.gen import UIAutomationClient  # type: ignore
except Exception:  # pragma: no cover
    pythoncom = None
    client = None
    UIAutomationClient = None


class ScrollCaptureThread(QThread):
    """Фоновый захват длинного окна через автоматический скролл."""

    progress_updated = Signal(int, int, str)
    capture_finished = Signal(list)
    error_occurred = Signal(str)

    MAX_FRAMES = 30

    def __init__(self, hwnd: int, parent=None) -> None:
        super().__init__(parent)
        self.hwnd = hwnd
        self.frames: List[np.ndarray] = []

    # ---- helpers ---------------------------------------------------
    def _is_hwnd_valid(self) -> bool:
        return bool(win32gui and win32gui.IsWindow(self.hwnd))

    def _capture_window(self) -> Optional[np.ndarray]:
        """Снимает окно через PrintWindow с fallback на BitBlt."""
        if not (win32gui and win32ui):
            return None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        except Exception:
            return None
        width, height = max(0, right - left), max(0, bottom - top)
        if width == 0 or height == 0:
            return None

        hwindc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwindc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        try:
            result = False
            if win32gui is not None:
                try:
                    result = bool(win32gui.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 1))
                except Exception:
                    result = False
            if not result:
                # Fallback BitBlt, помогает если PrintWindow рисует чёрный экран
                save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype=np.uint8)
            img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)
            # Конвертируем BGRA в RGBA
            img = img[..., [2, 1, 0, 3]]
            return img.copy()
        except Exception:
            return None
        finally:
            try:
                win32gui.DeleteObject(bitmap.GetHandle())
                save_dc.DeleteDC()
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwindc)
            except Exception:
                pass

    def _can_scroll(self) -> bool:
        if not (pythoncom and client and UIAutomationClient):
            return False
        try:
            pythoncom.CoInitialize()
            automation = client.CreateObject(UIAutomationClient.CUIAutomation)
            element = automation.ElementFromHandle(self.hwnd)
            pattern = element.GetCurrentPattern(UIAutomationClient.UIA_ScrollPatternId)
            if not pattern:
                return False
            vert_view_size = pattern.CurrentVerticalViewSize
            return bool(pattern.CurrentVerticallyScrollable and vert_view_size < 100)
        except Exception:
            return False
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _frames_similar(self, prev: np.ndarray, current: np.ndarray) -> bool:
        """Сравнивает нижние 20% предыдущего и верхние 20% текущего кадра."""
        if prev is None or current is None:
            return False
        h_prev, w_prev = prev.shape[:2]
        h_cur, w_cur = current.shape[:2]
        if h_prev == 0 or h_cur == 0:
            return False
        overlap_prev = max(1, int(h_prev * 0.2))
        overlap_cur = max(1, int(h_cur * 0.2))
        height = min(overlap_prev, overlap_cur)
        width = min(w_prev, w_cur)
        prev_crop = prev[h_prev - height : h_prev, :width, :3]
        cur_crop = current[:height, :width, :3]
        if prev_crop.size == 0 or cur_crop.size == 0:
            return False
        similarity = float(np.mean(np.isclose(prev_crop, cur_crop, atol=2)))
        return similarity >= 0.95

    def _send_scroll(self) -> None:
        if not (win32api and win32con):
            return
        try:
            win32api.SendMessage(self.hwnd, win32con.WM_VSCROLL, win32con.SB_PAGEDOWN, 0)
        except Exception:
            pass

    # ---- thread ----------------------------------------------------
    def run(self) -> None:  # noqa: D401 - логика потока
        if not self._is_hwnd_valid():
            self.error_occurred.emit("Окно недоступно или закрыто.")
            return

        scrollable = self._can_scroll()
        message = "Захват первого кадра"
        self.progress_updated.emit(0, self.MAX_FRAMES, message)

        first_frame = self._capture_window()
        if first_frame is None:
            self.error_occurred.emit("Не удалось снять содержимое окна.")
            return

        self.frames.append(first_frame)
        if not scrollable:
            # Окно не скроллится — возвращаем обычный скриншот
            self.progress_updated.emit(1, 1, "Окно не скроллится, сохранён одиночный кадр")
            self.capture_finished.emit(self.frames)
            return

        for idx in range(1, self.MAX_FRAMES):
            if self.isInterruptionRequested():
                break
            self._send_scroll()
            self.msleep(random.randint(300, 500))
            frame = self._capture_window()
            if frame is None:
                break
            if self._frames_similar(self.frames[-1], frame):
                # Достигнут конец содержимого
                break
            self.frames.append(frame)
            self.progress_updated.emit(idx + 1, self.MAX_FRAMES, f"Кадров собрано: {len(self.frames)}")

        self.capture_finished.emit(self.frames)
