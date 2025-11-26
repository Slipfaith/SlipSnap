
import sys
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QCursor, QGuiApplication

# Поскольку pywin32 недоступен в среде разработки,
# импортируем его с обработкой исключений.
# В целевой среде Windows он должен быть установлен.
try:
    import win32gui
    import win32con
    import win32api
except ImportError:
    # Создаем "заглушки" для работы в других ОС
    win32gui = None
    win32con = None
    win32api = None
    print("WARNING: pywin32 is not installed. CrosshairPicker will not work.")


class CrosshairWindowPicker(QWidget):
    """
    Полноэкранное прозрачное окно для выбора окна с помощью курсора-прицела.
    Подсвечивает окно под курсором и возвращает его HWND по клику.
    """
    window_selected = Signal(int)
    selection_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        if not win32gui:
            raise RuntimeError("pywin32 is required for this widget to function.")

        # Настройка окна: поверх всех, без рамки, как инструмент
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        # Включение полной прозрачности
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setCursor(Qt.CrossCursor)
        self.current_hwnd = None
        self.current_rect = None

        # Таймер для отслеживания окна под курсором
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(100)  # Обновляем 10 раз в секунду
        self.update_timer.timeout.connect(self._update_target_window)

    def showEvent(self, event):
        """При показе окна разворачиваем его на весь экран и запускаем таймер."""
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.update_timer.start()
        super().showEvent(event)

    def closeEvent(self, event):
        """При закрытии окна останавливаем таймер."""
        self.update_timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event):
        """Отрисовка рамки подсветки."""
        if self.current_rect:
            painter = QPainter(self)
            pen = QPen(QColor(255, 0, 0, 200), 3, Qt.SolidLine)
            painter.setPen(pen)

            # Рисуем прямоугольник. QRect ожидает (left, top, width, height)
            # GetWindowRect возвращает (left, top, right, bottom)
            left, top, right, bottom = self.current_rect
            width = right - left
            height = bottom - top

            painter.drawRect(left, top, width, height)

    def mousePressEvent(self, event):
        """При клике мыши отправляем сигнал с HWND и закрываемся."""
        if event.button() == Qt.LeftButton and self.current_hwnd:
            self.window_selected.emit(self.current_hwnd)
            self.close()
        event.accept()

    def keyPressEvent(self, event):
        """При нажатии ESC закрываемся без выбора."""
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()
        event.accept()

    def _update_target_window(self):
        """Обновляет информацию об окне под курсором."""
        pos = QCursor.pos()
        point = (pos.x(), pos.y())

        try:
            # Получаем HWND окна под курсором
            hwnd = win32gui.WindowFromPoint(point)

            # Пропускаем наше собственное окно и дочерние окна
            if hwnd == self.winId() or win32gui.IsChild(win32gui.GetParent(hwnd), hwnd):
                 # Если под курсором наше окно, пытаемся найти окно "под" ним.
                 # Для этого временно скрываем наше окно.
                self.setVisible(False)
                hwnd = win32gui.WindowFromPoint(point)
                self.setVisible(True)

            # Проверяем, изменилось ли окно
            if hwnd and hwnd != self.current_hwnd:
                # Игнорируем невидимые или отключенные окна
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd):
                    return

                self.current_hwnd = hwnd
                self.current_rect = win32gui.GetWindowRect(hwnd)
                self.update() # Запускаем перерисовку (paintEvent)

        except win32gui.error:
            # Окно могло исчезнуть, пока мы на него смотрели
            self.current_hwnd = None
            self.current_rect = None
            self.update()


def main():
    """Функция для демонстрации работы CrosshairWindowPicker."""
    app = QApplication(sys.argv)

    def on_select(hwnd):
        try:
            title = win32gui.GetWindowText(hwnd)
            print(f"Окно выбрано! HWND: {hwnd}, Заголовок: '{title}'")
        except win32gui.error:
            print(f"Не удалось получить заголовок для HWND: {hwnd}")

    def on_cancel():
        print("Выбор отменен.")
        app.quit()

    if not win32gui:
        print("Ошибка: pywin32 не установлен. Запуск невозможен.")
        sys.exit(1)

    print("Запуск Crosshair Picker. Кликните на окно или нажмите ESC.")
    picker = CrosshairWindowPicker()
    picker.window_selected.connect(on_select)
    picker.selection_cancelled.connect(on_cancel)
    picker.show()

    # Закрываем приложение после закрытия picker'а
    picker.finished.connect(app.quit)

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
