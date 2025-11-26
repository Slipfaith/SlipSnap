"""Overlay окно выбора целей с прицелом."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

try:
    import win32gui
except Exception:  # pragma: no cover - защищает не-Windows окружения
    win32gui = None


@dataclass
class _HighlightState:
    hwnd: int = 0
    rect: Optional[QRect] = None
    pulse: int = 0


class CrosshairWindowPicker(QWidget):
    """Полноэкранный прозрачный слой для выбора окна."""

    window_selected = Signal(int)
    selection_canceled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._state = _HighlightState()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._advance_pulse)
        self._pulse_timer.start(80)

    def start(self) -> None:
        """Показывает оверлей."""
        self._state = _HighlightState()
        # Покрываем всю виртуальную область, чтобы захват работал при нескольких мониторах
        geometry = QRect()
        for screen in QGuiApplication.screens():
            geometry = geometry.united(screen.geometry())
        if geometry.isValid():
            self.setGeometry(geometry)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _advance_pulse(self) -> None:
        self._state.pulse = (self._state.pulse + 1) % 10
        if self._state.rect:
            self.update()

    def _rect_from_hwnd(self, hwnd: int) -> Optional[QRect]:
        if not hwnd or not win32gui:
            return None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right <= left or bottom <= top:
                return None
            return QRect(left, top, right - left, bottom - top)
        except Exception:
            return None

    def _update_target(self, global_pos: QPoint) -> None:
        if not win32gui:
            return
        try:
            hwnd = int(win32gui.WindowFromPoint((global_pos.x(), global_pos.y())))
        except Exception:
            return

        # Игнорируем собственное окно выбора
        try:
            if hwnd and hwnd == int(self.winId()):
                return
        except Exception:
            pass

        rect = self._rect_from_hwnd(hwnd)
        if rect:
            self._state.hwnd = hwnd
            self._state.rect = rect
            self.update()

    # ---- Qt events -------------------------------------------------
    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - базовое описание
        self._update_target(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._state.hwnd:
            self.window_selected.emit(self._state.hwnd)
            self.close()
        elif event.button() == Qt.RightButton:
            self.selection_canceled.emit()
            self.close()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.selection_canceled.emit()
            self.close()
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: D401 - базовое описание
        if not self._state.rect:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Лёгкое затемнение вокруг выделяемого окна
        painter.fillRect(self.rect(), Qt.transparent)

        alpha = 120 + (self._state.pulse * 8)
        pen = QPen(Qt.red)
        pen.setWidth(3)
        pen.setColor(pen.color().withAlpha(max(60, min(alpha, 220))))
        painter.setPen(pen)
        painter.drawRect(self._state.rect.adjusted(1, 1, -1, -1))

    def closeEvent(self, event) -> None:  # noqa: D401 - базовое описание
        self._pulse_timer.stop()
        super().closeEvent(event)


if __name__ == "__main__":  # pragma: no cover - ручной тест
    app = QGuiApplication(sys.argv)
    picker = CrosshairWindowPicker()
    picker.window_selected.connect(lambda hwnd: print(f"Выбрано окно: {hwnd}"))
    picker.selection_canceled.connect(lambda: print("Отмена"))
    picker.start()
    sys.exit(app.exec())
