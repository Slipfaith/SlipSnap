"""Координатор скролл-захвата."""

from __future__ import annotations

import logging
import platform
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Qt
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
        self._configure_logging()

    def _configure_logging(self) -> None:
        """Готовит вывод логов в командную строку."""
        root_logger = logging.getLogger()
        if root_logger.handlers:
            return
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
        )
        logging.info("Логирование включено. Готов к запуску скролл-захвата.")

    def start(self) -> None:
        if platform.system().lower() != "windows":
            logging.error(
                "Скролл-захват не поддерживается: требуется Windows, текущая ОС: %s",
                platform.system(),
            )
            self.error_occurred.emit("Скролл-захват поддерживается только в Windows")
            return
        logging.info("Запущен выбор окна для скролл-захвата")
        self.selection_started.emit()
        self._picker = CrosshairWindowPicker()
        QApplication.setOverrideCursor(Qt.CrossCursor)
        self._picker.window_selected.connect(self._on_window_selected)
        self._picker.selection_canceled.connect(self._on_selection_canceled)
        self._picker.start()

    def _on_window_selected(self, hwnd: int) -> None:
        if not hwnd:
            logging.warning("Выбор окна отменён пользователем")
            self.error_occurred.emit("Окно не выбрано")
            return
        logging.info("Окно выбрано, hwnd=%s", hwnd)
        self.capture_started.emit(hwnd)
        self._thread = ScrollCaptureThread(hwnd)
        self._thread.progress_updated.connect(self._relay_progress)
        self._thread.capture_finished.connect(self._on_capture_finished)
        self._thread.error_occurred.connect(self.error_occurred)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_selection_canceled(self) -> None:
        logging.info("Пользователь отменил выбор окна")
        QApplication.restoreOverrideCursor()
        self.error_occurred.emit("Выбор отменён")

    def _relay_progress(self, current: int, total: int, message: str) -> None:
        percent = 0
        if total:
            percent = int((current / max(total, 1)) * 100)
        logging.info("Прогресс скролл-захвата: %s/%s (%s%%) — %s", current, total, percent, message)
        self.progress_updated.emit(percent, message)

    def _on_capture_finished(self, frames) -> None:
        if not frames:
            logging.error("Поток скролл-захвата завершился без кадров")
            self.error_occurred.emit("Кадры не получены")
            return
        try:
            output_dir = Path(tempfile.gettempdir()) / "slipsnap"
            output_path = output_dir / "scroll_capture.png"
            stitcher = ImageStitcher(frames)
            final_path = stitcher.stitch(output_path)
            logging.info("Скролл-захват успешно собран: %s", final_path)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Ошибка сборки скролла: %s", exc)
            self.error_occurred.emit(f"Ошибка сборки скролла: {exc}")
            return
        self.capture_completed.emit(str(final_path))

    def _cleanup_thread(self) -> None:
        logging.info("Очистка ресурсов потока скролл-захвата")
        self._thread = None
        QApplication.restoreOverrideCursor()
