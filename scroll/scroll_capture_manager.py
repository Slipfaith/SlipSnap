"""Координатор захвата с выбором окна и склейкой изображения."""
from __future__ import annotations

import os
import tempfile
from typing import List, Optional

from PySide6 import QtCore

from scroll.crosshair_picker import CrosshairWindowPicker
from scroll.image_stitcher import ImageStitcher
from scroll.scroll_capture import ScrollCaptureThread


class ScrollCaptureManager(QtCore.QObject):
    """Запускает выбор окна, захват и склейку результата."""

    selection_started = QtCore.Signal()
    capture_started = QtCore.Signal(int)
    progress_updated = QtCore.Signal(int, str)
    capture_completed = QtCore.Signal(str)
    error_occurred = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._picker: Optional[CrosshairWindowPicker] = None
        self._capture_thread: Optional[ScrollCaptureThread] = None
        self._stitcher = ImageStitcher()

    def start_selection(self) -> None:
        """Отображает окно выбора."""
        self.selection_started.emit()
        self._picker = CrosshairWindowPicker()
        self._picker.window_selected.connect(self._on_window_selected)
        self._picker.selection_canceled.connect(self._on_canceled)
        self._picker.start()

    def _on_canceled(self) -> None:
        self.error_occurred.emit("Выбор окна отменён")

    def _on_window_selected(self, hwnd: int) -> None:
        self.capture_started.emit(hwnd)
        if self._capture_thread and self._capture_thread.isRunning():
            self._capture_thread.request_stop()
        self._capture_thread = ScrollCaptureThread(hwnd)
        self._capture_thread.progress_updated.connect(self._relay_progress)
        self._capture_thread.capture_finished.connect(self._on_capture_finished)
        self._capture_thread.error_occurred.connect(self.error_occurred)
        self._capture_thread.start()

    def _relay_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / max(total, 1)) * 100)
        self.progress_updated.emit(percent, message)

    def _on_capture_finished(self, frames: List[np.ndarray]) -> None:
        if not frames:
            self.error_occurred.emit("Не удалось получить кадры")
            return
        try:
            output_dir = tempfile.mkdtemp(prefix="slipsnap_scroll_")
            output_path = os.path.join(output_dir, "scroll_capture.png")
            image_path = self._stitcher.stitch_frames(frames, output_path)
            self.capture_completed.emit(image_path)
        except Exception as exc:  # pragma: no cover
            self.error_occurred.emit(str(exc))

    def stop(self) -> None:
        """Останавливает текущий захват."""
        if self._capture_thread and self._capture_thread.isRunning():
            self._capture_thread.request_stop()
            self._capture_thread.wait(2000)
        if self._picker:
            self._picker.close()
            self._picker = None

