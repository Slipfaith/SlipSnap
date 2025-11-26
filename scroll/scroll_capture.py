
import time
import numpy as np
from PySide6.QtCore import QThread, Signal

# Блок импорта с обработкой исключений для pywin32 и comtypes
try:
    import win32gui
    import win32con
    import win32api
    import win32ui
    from comtypes.client import GetModule, CreateObject
    from comtypes import IID, CoInitialize, CoUninitialize
    # Загружаем библиотеку UIAutomationCore
    GetModule("UIAutomationCore.dll")
    import comtypes.gen.UIAutomationClient as UIA
    _pywin32_imported = True
except ImportError:
    _pywin32_imported = False
    print("WARNING: pywin32 or comtypes is not installed. ScrollCapture will not work.")

from PIL import Image


class ScrollCaptureThread(QThread):
    """
    Поток для выполнения автоматического скролл-захвата окна.
    Принимает HWND, проверяет возможность прокрутки, захватывает кадры
    и передает их в виде списка numpy-массивов.
    """
    capture_finished = Signal(list)
    progress_updated = Signal(int, int, str)
    error_occurred = Signal(str)

    MAX_FRAMES = 30
    SCROLL_WAIT_MS = 400
    SIMILARITY_THRESHOLD = 0.98  # Порог для определения конца прокрутки

    def __init__(self, hwnd, parent=None):
        super().__init__(parent)
        if not _pywin32_imported:
            raise RuntimeError("pywin32 and comtypes are required for this thread.")

        self.hwnd = hwnd
        self.frames = []

    def run(self):
        """Основной метод потока, выполняющий захват."""
        try:
            CoInitialize()  # Инициализация COM для этого потока

            if not win32gui.IsWindow(self.hwnd):
                self.error_occurred.emit("Окно больше не существует.")
                return

            if not self._is_scrollable():
                self.progress_updated.emit(0, 1, "Окно не поддерживает прокрутку. Захват одного кадра.")
                frame = self._capture_window()
                if frame is not None:
                    self.frames.append(frame)
                self.progress_updated.emit(1, 1, "Завершено.")
                self.capture_finished.emit(self.frames)
                return

            self._capture_loop()

        except Exception as e:
            self.error_occurred.emit(f"Произошла критическая ошибка: {e}")
        finally:
            CoUninitialize() # Обязательно деинициализируем COM

    def _capture_loop(self):
        """Цикл захвата кадров с прокруткой."""
        self.progress_updated.emit(0, self.MAX_FRAMES, "Начало захвата...")

        # Первый кадр
        initial_frame = self._capture_window()
        if initial_frame is None:
            self.error_occurred.emit("Не удалось захватить первый кадр.")
            return
        self.frames.append(initial_frame)

        for i in range(1, self.MAX_FRAMES):
            if not win32gui.IsWindow(self.hwnd):
                self.error_occurred.emit("Окно было закрыто во время захвата.")
                break

            self.progress_updated.emit(i, self.MAX_FRAMES, f"Захват кадра {i}...")

            prev_frame = self.frames[-1]

            # Прокрутка
            win32api.SendMessage(self.hwnd, win32con.WM_VSCROLL, win32con.SB_PAGEDOWN, 0)
            self.msleep(self.SCROLL_WAIT_MS)

            # Захват нового кадра
            new_frame = self._capture_window()
            if new_frame is None:
                # Ошибка захвата, возможно, окно свернулось
                self.error_occurred.emit("Не удалось захватить следующий кадр.")
                break

            # Сравнение с предыдущим кадром
            if self._are_images_similar(prev_frame, new_frame):
                self.progress_updated.emit(i, self.MAX_FRAMES, "Достигнут конец прокрутки.")
                break

            self.frames.append(new_frame)

        self.progress_updated.emit(len(self.frames), self.MAX_FRAMES, "Захват завершен.")
        self.capture_finished.emit(self.frames)

    def _capture_window(self):
        """Захватывает изображение окна с помощью PrintWindow или BitBlt."""
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width <= 0 or height <= 0:
                return None

            hwnd_dc = win32gui.GetWindowDC(self.hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(save_bitmap)

            # Используем PrintWindow для захвата содержимого, включая невидимые части
            # Флаг 2 (PW_CLIENTONLY) может помочь избежать захвата рамки окна
            result = win32gui.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 2)

            if result != 1:
                # PrintWindow не сработал, пробуем BitBlt с рабочего стола
                # Это захватит только видимую часть
                src_dc = win32gui.GetDC(0)
                save_dc.BitBlt((0, 0), (width, height), win32ui.CreateDCFromHandle(src_dc), (rect[0], rect[1]), win32con.SRCCOPY)
                win32gui.ReleaseDC(0, src_dc)

            bmp_info = save_bitmap.GetInfo()
            bmp_str = save_bitmap.GetBitmapBits(True)

            img = Image.frombuffer(
                'RGB',
                (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_str, 'raw', 'BGRX', 0, 1)

            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwnd_dc)

            # Проверка на "черный экран"
            if np.mean(np.array(img)) < 10:
                print("Warning: Captured image is mostly black.")

            return np.array(img)

        except (win32ui.error, win32gui.error) as e:
            print(f"Ошибка захвата окна: {e}")
            return None

    def _is_scrollable(self):
        """Проверяет, имеет ли окно вертикальную полосу прокрутки через UIAutomation."""
        try:
            ui_auto = CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation)
            element = ui_auto.ElementFromHandle(self.hwnd)

            # Получаем ScrollPattern
            scroll_pattern = element.GetCurrentPattern(UIA.UIA_ScrollPatternId)
            if scroll_pattern:
                properties = scroll_pattern.Current
                return properties.VerticallyScrollable
            return False
        except Exception as e:
            # Если UIAutomation не сработал, считаем, что прокрутки нет
            print(f"Не удалось проверить возможность прокрутки через UIAutomation: {e}")
            return False

    def _are_images_similar(self, img1, img2):
        """Сравнивает два изображения (numpy arrays) и возвращает True, если они похожи."""
        if img1.shape != img2.shape:
            return False

        # Простое и быстрое сравнение
        diff = np.sum(img1 != img2)
        total_pixels = img1.shape[0] * img1.shape[1] * img1.shape[2]
        similarity = 1.0 - (diff / total_pixels)

        return similarity >= self.SIMILARITY_THRESHOLD
