"""Ручной панорамный захват фиксированной области экрана."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

import cv2
import mss
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout

from scroll.image_stitcher import ImageStitcher

if TYPE_CHECKING:  # pragma: no cover - used only for type hints
    from gui import OverlayManager


class _PanoramicCaptureThread(QThread):
    frame_captured = Signal(int)
    finished_frames = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, region: Tuple[int, int, int, int], interval_ms: int = 380) -> None:
        super().__init__()
        self.region = region
        self.interval_ms = max(50, interval_ms)

    def run(self) -> None:  # noqa: D401 - поток захвата кадров
        left, top, width, height = self.region
        frames = []
        try:
            with mss.mss() as sct:
                monitor = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
                while not self.isInterruptionRequested():
                    shot = sct.grab(monitor)
                    frame = np.array(shot)
                    if frame.shape[2] == 4:  # BGRA -> RGBA
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
                    frames.append(frame)
                    self.frame_captured.emit(len(frames))
                    self.msleep(self.interval_ms)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Ошибка панорамного захвата: %s", exc)
            self.error_occurred.emit(f"Не удалось выполнить захват: {exc}")
            return

        if frames:
            self.finished_frames.emit(frames)
        else:
            self.error_occurred.emit("Кадры не получены")


class PanoramicControlDialog(QDialog):
    start_requested = Signal()
    stop_requested = Signal()
    canceled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panoramic Capture")
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.hint = QLabel("Закреплена область. Нажмите Start и прокручивайте страницу.")
        self.frames_label = QLabel("Кадров: 0")
        layout.addWidget(self.hint)
        layout.addWidget(self.frames_label)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_stop.setEnabled(False)

        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_cancel.clicked.connect(self._on_cancel)

        buttons.addWidget(self.btn_start)
        buttons.addWidget(self.btn_stop)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)

    def _on_start(self) -> None:
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.start_requested.emit()

    def _on_stop(self) -> None:
        self.btn_stop.setEnabled(False)
        self.stop_requested.emit()

    def _on_cancel(self) -> None:
        self.canceled.emit()
        self.close()

    def update_frames(self, count: int) -> None:
        self.frames_label.setText(f"Кадров: {count}")


class PanoramicCaptureManager(QObject):
    """Организует ручной панорамный захват фиксированной области."""

    selection_started = Signal()
    selection_canceled = Signal()
    capture_started = Signal()
    frame_captured = Signal(int)
    capture_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._overlay: Optional["OverlayManager"] = None
        self._thread: Optional[_PanoramicCaptureThread] = None
        self._dialog: Optional[PanoramicControlDialog] = None
        self._selected_region: Optional[Tuple[int, int, int, int]] = None

    # ---- selection ----
    def start(self) -> None:
        self.selection_started.emit()
        from gui import OverlayManager

        self._overlay = OverlayManager(self.cfg)
        self._overlay.region_selected.connect(self._on_region_selected)
        self._overlay.finished.connect(self._on_selection_finished)
        self._overlay.start_region_selection()

    def _on_region_selected(self, rect: tuple) -> None:
        self._selected_region = tuple(map(int, rect))  # type: ignore[arg-type]
        self._overlay = None
        self._show_dialog()

    def _on_selection_finished(self) -> None:
        if self._selected_region is None:
            self.error_occurred.emit("Выбор области отменён")

    # ---- dialog ----
    def _show_dialog(self) -> None:
        self._dialog = PanoramicControlDialog()
        self._dialog.start_requested.connect(self._begin_capture)
        self._dialog.stop_requested.connect(self.stop)
        self._dialog.canceled.connect(self._cancel)
        self._dialog.show()

    def _cancel(self) -> None:
        self.stop()
        self.selection_canceled.emit()
        if self._dialog:
            self._dialog.close()

    # ---- capture ----
    def _begin_capture(self) -> None:
        if not self._selected_region:
            self.error_occurred.emit("Область захвата не выбрана")
            return
        if self._thread and self._thread.isRunning():
            return
        self._thread = _PanoramicCaptureThread(self._selected_region)
        self._thread.frame_captured.connect(self._on_frame_captured)
        self._thread.finished_frames.connect(self._on_capture_finished)
        self._thread.error_occurred.connect(self._on_capture_error)
        self._thread.finished.connect(self._cleanup_thread)
        self.capture_started.emit()
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()

    def _on_frame_captured(self, count: int) -> None:
        self.frame_captured.emit(count)
        if self._dialog:
            self._dialog.update_frames(count)

    def _on_capture_finished(self, frames: list) -> None:
        try:
            output_dir = Path(tempfile.gettempdir()) / "slipsnap"
            output_path = output_dir / "panoramic_capture.png"
            stitcher = ImageStitcher(frames)
            final_path = stitcher.stitch(output_path)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Ошибка склейки панорамы: %s", exc)
            self.error_occurred.emit(f"Не удалось собрать панораму: {exc}")
            return

        if self._dialog:
            self._dialog.close()
        QApplication.restoreOverrideCursor()
        self.capture_completed.emit(str(final_path))

    def _on_capture_error(self, message: str) -> None:
        if self._dialog:
            self._dialog.close()
        self.error_occurred.emit(message)

    def _cleanup_thread(self) -> None:
        self._thread = None

