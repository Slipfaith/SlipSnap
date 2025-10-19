from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Qt

def _pm(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    return pm

def make_icon_capture(size: int = 28) -> QIcon:
    """Рамка с прицелом — «Сделать снимок»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    # Рамка
    p.setPen(QPen(QColor(240, 240, 240), 2))
    m = 5
    p.drawRect(m, m, size - 2 * m, size - 2 * m)
    # Прицел
    p.drawLine(size // 2, m + 3, size // 2, size - m - 3)
    p.drawLine(m + 3, size // 2, size - m - 3, size // 2)
    p.end()
    return QIcon(pm)

def make_icon_shape(shape: str = "rect", size: int = 24) -> QIcon:
    """Переключатель формы выделения: rect/ellipse"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(240, 240, 240), 2))
    m = 5
    if shape == "ellipse":
        p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    else:
        p.drawRect(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return QIcon(pm)

def make_icon_close(size: int = 28) -> QIcon:
    """Крестик — «Закрыть»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(240, 80, 80), 2.5))
    m = 7
    p.drawLine(m, m, size - m, size - m)
    p.drawLine(size - m, m, m, size - m)
    p.end()
    return QIcon(pm)

def make_icon_add(size: int = 28) -> QIcon:
    """Плюс в круге — «Добавить»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(70, 130, 240), 2))
    m = 5
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.drawLine(size // 2, m + 4, size // 2, size - m - 4)
    p.drawLine(m + 4, size // 2, size - m - 4, size // 2)
    p.end()
    return QIcon(pm)

def make_icon_collage(size: int = 28) -> QIcon:
    """Сетка 2×2 — «Коллаж»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(120, 120, 120), 2))
    m = 5
    # Внешняя рамка
    p.drawRect(m, m, size - 2 * m, size - 2 * m)
    # Разделители
    cx = size // 2
    cy = size // 2
    p.drawLine(cx, m, cx, size - m)
    p.drawLine(m, cy, size - m, cy)
    p.end()
    return QIcon(pm)


def make_icon_series(size: int = 28) -> QIcon:
    """Две перекрывающиеся рамки — «Серия»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(180, 200, 255), 2)
    p.setPen(pen)
    m = 6
    offset = 4
    # Задняя рамка
    p.drawRoundedRect(m + offset, m, size - 2 * m, size - 2 * m, 6, 6)
    # Передняя рамка
    p.setPen(QPen(QColor(70, 130, 240), 2))
    p.drawRoundedRect(m, m + offset, size - 2 * m, size - 2 * m, 6, 6)
    # Индикатор счётчика
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.drawLine(size // 2 - 3, size - m - 2, size // 2 + 4, size - m - 2)
    p.end()
    return QIcon(pm)
