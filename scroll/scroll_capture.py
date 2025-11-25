"""Поток автоматического скролл-захвата окна."""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np
from PySide6 import QtCore

try:
    import win32api
    import win32con
    import win32gui
    import win32ui
except Exception as exc:  # pragma: no cover - платформа без win32
    raise ImportError("scroll_capture доступен только под Windows") from exc

try:
    import comtypes.client  # type: ignore
except Exception:
    comtypes = None  # type: ignore


class ScrollCaptureThread(QtCore.QThread):
    """Захватывает прокручиваемое окно постранично."""

    progress_updated = QtCore.Signal(int, int, str)
    capture_finished = QtCore.Signal(list)
    error_occurred = QtCore.Signal(str)

    def __init__(self, hwnd: int, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.hwnd = hwnd
        self._frames: List[np.ndarray] = []
        self._stop_requested = False

    def request_stop(self) -> None:
        """Останавливает поток захвата."""
        self._stop_requested = True

    def run(self) -> None:  # noqa: D401
        """Точка входа QThread."""
        if not win32gui.IsWindow(self.hwnd):
            self.error_occurred.emit("Окно недоступно или было закрыто")
            return
        try:
            scrollable = self._check_scrollable()
        except Exception:
            scrollable = False
        if not scrollable:
            # fallback: один кадр без скролла
            try:
                frame = self._capture_frame()
                if frame is not None:
                    self._frames.append(frame)
                    self.capture_finished.emit(self._frames)
                else:
                    self.error_occurred.emit("Не удалось захватить окно")
            except Exception as exc:  # pragma: no cover
                self.error_occurred.emit(str(exc))
            return

        total_limit = 30
        try:
            first = self._capture_frame()
            if first is None:
                self.error_occurred.emit("Пустой кадр при первом захвате")
                return
            self._frames.append(first)
            last_frame = first
            for index in range(1, total_limit + 1):
                if self._stop_requested or not win32gui.IsWindow(self.hwnd):
                    break
                self._scroll_once()
                time.sleep(0.35)
                next_frame = self._capture_frame()
                if next_frame is None:
                    break
                if self._is_overlap_repeat(last_frame, next_frame):
                    # достигнут конец
                    break
                self._frames.append(next_frame)
                last_frame = next_frame
                self.progress_updated.emit(index, total_limit, "Склейка кадров")
            self.capture_finished.emit(self._frames)
        except Exception as exc:  # pragma: no cover
            self.error_occurred.emit(str(exc))

    def _check_scrollable(self) -> bool:
        """Проверяет наличие ScrollPattern через UIAutomation."""
        if comtypes is None:
            return False
        try:
            iuia = comtypes.client.CreateObject("UIAutomationClient.CUIAutomation")
            element = iuia.ElementFromHandle(int(self.hwnd))
            scroll_pattern = element.GetCurrentPattern(10004)  # UIA_PatternIds.ScrollPatternId
            return scroll_pattern is not None
        except Exception:
            return False

    def _capture_frame(self) -> Optional[np.ndarray]:
        """Захватывает окно через PrintWindow, при ошибке пробует BitBlt."""
        if not win32gui.IsWindow(self.hwnd):
            return None
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        if width <= 1 or height <= 1:
            return None
        hwnd_dc = None
        mfc_dc = None
        save_dc = None
        bitmap = None
        try:
            hwnd_dc = win32gui.GetWindowDC(self.hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)
            result = win32gui.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 0)
            if not result:
                # fallback на BitBlt
                save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype=np.uint8)
            img.shape = (bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)
            # BGRX -> RGB
            return img[:, :, :3][:, :, ::-1].copy()
        except Exception:
            return None
        finally:
            try:
                if hwnd_dc:
                    win32gui.ReleaseDC(self.hwnd, hwnd_dc)
            finally:
                for obj in (bitmap, save_dc, mfc_dc):
                    try:
                        if obj:
                            obj.DeleteObject()
                    except Exception:
                        pass

    def _scroll_once(self) -> None:
        """Отправляет сообщение скролла вниз."""
        try:
            win32api.SendMessage(self.hwnd, win32con.WM_VSCROLL, win32con.SB_PAGEDOWN, 0)
        except Exception:
            pass

    def _is_overlap_repeat(self, prev: np.ndarray, current: np.ndarray) -> bool:
        """Сравнивает нижние 20% предыдущего кадра с верхом текущего."""
        if prev is None or current is None:
            return False
        if prev.shape[1] != current.shape[1]:
            # разные размеры, не считаем совпадением
            return False
        overlap_height = max(int(prev.shape[0] * 0.2), 1)
        prev_slice = prev[-overlap_height:]
        curr_slice = current[:overlap_height]
        if prev_slice.size == 0 or curr_slice.size == 0:
            return False
        try:
            equal_pixels = np.mean(prev_slice == curr_slice)
            return equal_pixels >= 0.95
        except Exception:
            return False
