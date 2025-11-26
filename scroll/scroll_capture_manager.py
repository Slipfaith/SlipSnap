"""Координатор скролл-захвата."""

from __future__ import annotations

import platform
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from scroll.crosshair_picker import CrosshairWindowPicker
from scroll.image_stitcher import ImageStitcher
from scroll.scroll_capture import ScrollCaptureThread


class ScrollCaptureManager(QObject):
    """Запускает выбор окна и собирает длинный скриншот."""

    selection_started = Signal()
    capture_started = Signal(int)
    progress_updated = Signal(int, str)
    capture_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._picker: Optional[CrosshairWindowPicker] = None
        self._thread: Optional[ScrollCaptureThread] = None

    def start(self) -> None:
        if platform.system().lower() != "windows":
            self.error_occurred.emit("Скролл-захват поддерживается только в Windows")
            return
        self.selection_started.emit()
        self._picker = CrosshairWindowPicker()
        self._picker.window_selected.connect(self._on_window_selected)
        self._picker.selection_canceled.connect(lambda: self.error_occurred.emit("Выбор отменён"))
        self._picker.start()

    def _on_window_selected(self, hwnd: int) -> None:
        if not hwnd:
            self.error_occurred.emit("Окно не выбрано")
            return
        self.capture_started.emit(hwnd)
        self._thread = ScrollCaptureThread(hwnd)
        self._thread.progress_updated.connect(self._relay_progress)
        self._thread.capture_finished.connect(self._on_capture_finished)
        self._thread.error_occurred.connect(self.error_occurred)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _relay_progress(self, current: int, total: int, message: str) -> None:
        percent = 0
        if total:
            percent = int((current / max(total, 1)) * 100)
        self.progress_updated.emit(percent, message)

    def _on_capture_finished(self, frames) -> None:
        if not frames:
            self.error_occurred.emit("Кадры не получены")
            return
        try:
            output_dir = Path(tempfile.gettempdir()) / "slipsnap"
            output_path = output_dir / "scroll_capture.png"
            stitcher = ImageStitcher(frames)
            final_path = stitcher.stitch(output_path)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(f"Ошибка сборки скролла: {exc}")
            return
        self.capture_completed.emit(str(final_path))

    def _cleanup_thread(self) -> None:
        self._thread = None
        QApplication.restoreOverrideCursor()
