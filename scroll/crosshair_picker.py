"""Overlay окно для выбора целевого окна через курсор-прицел.

Работает только под Windows (использует pywin32). При наведении подсвечивает
окно под курсором и по клику возвращает его HWND.
"""
from __future__ import annotations

import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

try:
    import win32gui
except Exception as exc:  # pragma: no cover - платформа без win32
    raise ImportError(
        "crosshair_picker доступен только под Windows с установленным pywin32"
    ) from exc


class CrosshairWindowPicker(QtWidgets.QWidget):
    """Полноэкранный прозрачный оверлей с подсветкой окна под курсором."""

    window_selected = QtCore.Signal(int)
    selection_canceled = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setMouseTracking(True)
        self._current_hwnd: Optional[int] = None
        self._current_rect: Optional[QtCore.QRect] = None
        # Заставляем окно быть полноэкранным на всех мониторах
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())

    def start(self) -> None:
        """Отображает окно выбора."""
        self.showFullScreen()
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 1))
        if self._current_rect:
            pen = QtGui.QPen(QtGui.QColor(0, 153, 255, 200), 3)
            painter.setPen(pen)
            # Легкая анимация за счёт пунктирной линии
            pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._current_rect.adjusted(1, 1, -1, -1))
        painter.end()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Escape:
            self.selection_canceled.emit()
            self.close()
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        global_pos = event.globalPosition().toPoint()
        try:
            hwnd = win32gui.WindowFromPoint((global_pos.x(), global_pos.y()))
        except Exception:
            hwnd = None
        if hwnd:
            try:
                rect = win32gui.GetWindowRect(hwnd)
            except Exception:
                rect = None
            if rect:
                # Координаты в Qt-прямоугольник
                self._current_hwnd = hwnd
                self._current_rect = QtCore.QRect(
                    rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
                )
                self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self._current_hwnd:
            self.window_selected.emit(int(self._current_hwnd))
            self.close()
            return
        super().mousePressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        # Безопасно сбрасываем состояние
        self._current_hwnd = None
        self._current_rect = None
        super().closeEvent(event)


if __name__ == "__main__":  # pragma: no cover - ручной тест
    app = QtWidgets.QApplication(sys.argv)
    picker = CrosshairWindowPicker()
    picker.window_selected.connect(lambda h: print(f"Selected HWND: {h}"))
    picker.selection_canceled.connect(lambda: print("Selection canceled"))
    picker.start()
    sys.exit(app.exec())
