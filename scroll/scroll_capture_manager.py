
import os
import tempfile
from PySide6.QtCore import QObject, Signal, Slot
from typing import List

# Импортируем созданные нами модули
from .crosshair_picker import CrosshairWindowPicker
from .scroll_capture import ScrollCaptureThread
from .image_stitcher import ImageStitcher

# Блок импорта с обработкой исключений на случай, если pywin32 не установлен
try:
    _pywin32_imported = True
    import win32gui
except ImportError:
    _pywin32_imported = False


class ScrollCaptureManager(QObject):
    """
    Координирует процесс скролл-захвата: от выбора окна до сохранения итогового изображения.
    """
    # --- Сигналы для информирования внешнего мира о состоянии процесса ---

    # Процесс выбора окна начался
    selection_started = Signal()
    # Окно было выбрано, и захват начался
    capture_started = Signal(int) # hwnd
    # Обновление прогресса (в процентах)
    progress_updated = Signal(int, str) # percent, message
    # Захват и склейка успешно завершены
    capture_completed = Signal(str) # image_path
    # Произошла ошибка на одном из этапов
    error_occurred = Signal(str) # error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        if not _pywin32_imported:
            # Эта проверка важна, чтобы избежать падения при инициализации
            # на системах без Windows.
            raise RuntimeError("Модуль pywin32 не найден. ScrollCaptureManager не может работать.")

        self.picker = None
        self.capture_thread = None

    @Slot()
    def start_capture(self):
        """
        Запускает полный цикл скролл-захвата, начиная с выбора окна.
        """
        try:
            self.selection_started.emit()

            # 1. Создаем и показываем окно выбора
            self.picker = CrosshairWindowPicker()
            self.picker.window_selected.connect(self._on_window_selected)
            self.picker.selection_cancelled.connect(self._on_selection_cancelled)
            # Если окно закроется по другой причине (не ESC и не клик)
            self.picker.finished.connect(self._on_picker_closed)
            self.picker.show()

        except Exception as e:
            self.error_occurred.emit(f"Не удалось запустить выбор окна: {e}")
            self.picker = None

    @Slot(int)
    def _on_window_selected(self, hwnd: int):
        """
        Обработчик сигнала выбора окна. Запускает поток захвата.
        """
        try:
            if not win32gui.IsWindow(hwnd):
                self.error_occurred.emit("Выбранное окно больше не существует.")
                return

            self.capture_started.emit(hwnd)

            # 2. Создаем и запускаем поток для захвата кадров
            self.capture_thread = ScrollCaptureThread(hwnd)
            self.capture_thread.capture_finished.connect(self._on_capture_finished)
            self.capture_thread.progress_updated.connect(self._on_capture_progress)
            self.capture_thread.error_occurred.connect(self.error_occurred)
            # Очищаем ссылку на поток после его завершения
            self.capture_thread.finished.connect(self._on_thread_finished)

            self.capture_thread.start()
        except Exception as e:
            self.error_occurred.emit(f"Не удалось начать захват: {e}")
            self.capture_thread = None

    @Slot()
    def _on_selection_cancelled(self):
        """Обработчик отмены выбора."""
        self.error_occurred.emit("Выбор окна был отменен.")

    @Slot()
    def _on_picker_closed(self):
        """Очистка после закрытия окна выбора."""
        self.picker = None

    @Slot(int, int, str)
    def _on_capture_progress(self, current: int, total: int, message: str):
        """Ретранслирует прогресс захвата в процентах."""
        percent = int((current / total) * 100) if total > 0 else 100
        self.progress_updated.emit(percent, message)

    @Slot(list)
    def _on_capture_finished(self, frames: List[np.ndarray]):
        """
        Обработчик завершения захвата. Запускает склейку изображений.
        """
        if not frames:
            self.error_occurred.emit("Захват не вернул ни одного кадра.")
            return

        self.progress_updated.emit(100, "Захвачено кадров: {}. Начинаю склейку...".format(len(frames)))

        try:
            # 3. Склеиваем полученные кадры
            stitcher = ImageStitcher(frames)

            # Создаем временный файл для сохранения результата
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"slipsnap_scroll_{os.urandom(4).hex()}.png")

            final_path = stitcher.stitch_and_save(output_path)

            self.progress_updated.emit(100, "Склейка завершена.")
            self.capture_completed.emit(final_path)

        except Exception as e:
            self.error_occurred.emit(f"Ошибка при склейке изображений: {e}")

    @Slot()
    def _on_thread_finished(self):
        """Очистка после завершения потока захвата."""
        self.capture_thread = None
