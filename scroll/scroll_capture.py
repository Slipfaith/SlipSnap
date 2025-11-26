"""Поток автоматического скролл-захвата окна."""

from __future__ import annotations

import random
from typing import List, Optional

import cv2
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
    MAX_FRAMES_CAP = 200

    def __init__(self, hwnd: int, parent=None) -> None:
        super().__init__(parent)
        self.hwnd = hwnd
        self.frames: List[np.ndarray] = []
        self._automation = None
        self._co_initialized = False
        self._initial_scroll_percent: Optional[float] = None
        self._max_frames = self.MAX_FRAMES
        self._base_width: Optional[int] = None

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

        hwindc = None
        mfc_dc = None
        save_dc = None
        bitmap = None

        try:
            hwindc = win32gui.GetWindowDC(self.hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwindc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)

            result = False
            if win32gui is not None:
                try:
                    result = bool(win32gui.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 1))
                except Exception:
                    result = False
            if not result and win32con is not None:
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
                if bitmap is not None:
                    win32gui.DeleteObject(bitmap.GetHandle())
                if save_dc is not None:
                    save_dc.DeleteDC()
                if mfc_dc is not None:
                    mfc_dc.DeleteDC()
                if hwindc is not None:
                    win32gui.ReleaseDC(self.hwnd, hwindc)
            except Exception:
                pass

    def _get_scroll_pattern(self):
        if not self._automation:
            return None
        try:
            element = self._automation.ElementFromHandle(self.hwnd)
            pattern = element.GetCurrentPattern(UIAutomationClient.UIA_ScrollPatternId)
            return pattern
        except Exception:
            return None

    def _can_scroll(self) -> bool:
        pattern = self._get_scroll_pattern()
        if not pattern:
            return False
        try:
            vert_view_size = pattern.CurrentVerticalViewSize
            return bool(pattern.CurrentVerticallyScrollable and vert_view_size < 100)
        except Exception:
            return False

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

    def _frames_duplicate(self, prev: np.ndarray, current: np.ndarray) -> bool:
        if prev is None or current is None:
            return False
        if prev.shape[:2] != current.shape[:2]:
            return False
        small_prev = cv2.resize(prev[:, :, :3], (32, 32), interpolation=cv2.INTER_AREA)
        small_current = cv2.resize(current[:, :, :3], (32, 32), interpolation=cv2.INTER_AREA)
        diff = np.mean(np.abs(small_prev.astype(np.int16) - small_current.astype(np.int16)))
        return diff <= 1.5

    def _normalize_frame_size(self, frame: np.ndarray) -> np.ndarray:
        if self._base_width is None:
            self._base_width = frame.shape[1]
            return frame
        if frame.shape[1] == self._base_width:
            return frame
        scale = self._base_width / max(1, frame.shape[1])
        new_height = max(1, int(frame.shape[0] * scale))
        resized = cv2.resize(frame, (self._base_width, new_height), interpolation=cv2.INTER_AREA)
        return resized

    def _ensure_focus(self) -> None:
        if not win32gui:
            return
        try:
            win32gui.SetForegroundWindow(self.hwnd)
            try:
                win32gui.BringWindowToTop(self.hwnd)
            except Exception:
                pass
        except Exception:
            pass

    def _send_scroll(self) -> None:
        if not (win32api and win32con):
            return
        try:
            self._ensure_focus()
            win32api.SendMessage(self.hwnd, win32con.WM_VSCROLL, win32con.SB_PAGEDOWN, 0)
        except Exception:
            pass

    def _estimate_max_frames(self) -> int:
        pattern = self._get_scroll_pattern()
        if not pattern:
            return self.MAX_FRAMES
        try:
            view_size = pattern.CurrentVerticalViewSize
            if view_size <= 0 or view_size >= 100:
                return self.MAX_FRAMES
            estimated = int(np.ceil(100 / view_size)) + 2
            return int(max(self.MAX_FRAMES, min(self.MAX_FRAMES_CAP, estimated)))
        except Exception:
            return self.MAX_FRAMES

    def _restore_scroll(self) -> None:
        pattern = self._get_scroll_pattern()
        if pattern and self._initial_scroll_percent is not None:
            try:
                pattern.SetScrollPercent(pattern.CurrentHorizontalScrollPercent, self._initial_scroll_percent)
                return
            except Exception:
                pass
        if win32api and win32con:
            try:
                win32api.SendMessage(self.hwnd, win32con.WM_VSCROLL, win32con.SB_TOP, 0)
            except Exception:
                pass

    # ---- thread ----------------------------------------------------
    def run(self) -> None:  # noqa: D401 - логика потока
        if not self._is_hwnd_valid():
            self.error_occurred.emit("Окно недоступно или закрыто.")
            return

        try:
            if pythoncom:
                try:
                    pythoncom.CoInitialize()
                    self._co_initialized = True
                except Exception:
                    self._co_initialized = False
            if client and UIAutomationClient:
                try:
                    self._automation = client.CreateObject(UIAutomationClient.CUIAutomation)
                except Exception:
                    self._automation = None

            scrollable = self._can_scroll()
            self._max_frames = self._estimate_max_frames()
            message = "Захват первого кадра"
            self.progress_updated.emit(0, self._max_frames, message)

            first_frame = self._capture_window()
            if first_frame is None:
                self.error_occurred.emit("Не удалось снять содержимое окна.")
                return
            first_frame = self._normalize_frame_size(first_frame)
            self.frames.append(first_frame)

            pattern = self._get_scroll_pattern()
            if pattern:
                try:
                    self._initial_scroll_percent = pattern.CurrentVerticalScrollPercent
                except Exception:
                    self._initial_scroll_percent = None

            if not scrollable:
                # Окно не скроллится — возвращаем обычный скриншот
                self.progress_updated.emit(1, 1, "Окно не скроллится, сохранён одиночный кадр")
                self.capture_finished.emit(self.frames)
                return

            duplicate_streak = 0
            for idx in range(1, self._max_frames):
                if self.isInterruptionRequested():
                    break
                self._send_scroll()
                self.msleep(random.randint(300, 500))
                frame = self._capture_window()
                if frame is None:
                    break
                frame = self._normalize_frame_size(frame)
                if self._frames_similar(self.frames[-1], frame):
                    duplicate_streak += 1
                    if duplicate_streak >= 2:
                        break
                    continue
                if self._frames_duplicate(self.frames[-1], frame):
                    continue
                duplicate_streak = 0
                self.frames.append(frame)
                self.progress_updated.emit(idx + 1, self._max_frames, f"Кадров собрано: {len(self.frames)}")

            self.capture_finished.emit(self.frames)
        finally:
            self._restore_scroll()
            if self._co_initialized and pythoncom:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
