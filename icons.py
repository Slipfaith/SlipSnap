from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt

from design_tokens import Palette, Metrics

def _pm(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    return pm

def make_icon_capture(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Рамка с прицелом — «Сделать снимок»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    # Рамка
    p.setPen(QPen(QColor(*Palette.ICON_BASE), 2))
    m = Metrics.ICON_MARGIN_SMALL
    p.drawRect(m, m, size - 2 * m, size - 2 * m)
    # Прицел
    p.drawLine(size // 2, m + 3, size // 2, size - m - 3)
    p.drawLine(m + 3, size // 2, size - m - 3, size // 2)
    p.end()
    return QIcon(pm)

def make_icon_shape(shape: str = "rect", size: int = Metrics.ICON_SHAPE) -> QIcon:
    """Переключатель формы выделения: rect/ellipse"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(*Palette.ICON_BASE), 2))
    m = Metrics.ICON_MARGIN_SMALL
    if shape == "ellipse":
        p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    else:
        p.drawRect(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return QIcon(pm)

def make_icon_close(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Крестик — «Закрыть»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(*Palette.ICON_WARNING), 2.5))
    m = Metrics.ICON_MARGIN_MEDIUM
    p.drawLine(m, m, size - m, size - m)
    p.drawLine(size - m, m, m, size - m)
    p.end()
    return QIcon(pm)

def make_icon_add(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Плюс в круге — «Добавить»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(*Palette.ICON_POSITIVE), 2))
    m = Metrics.ICON_MARGIN_SMALL
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.drawLine(size // 2, m + 4, size // 2, size - m - 4)
    p.drawLine(m + 4, size // 2, size - m - 4, size // 2)
    p.end()
    return QIcon(pm)

def make_icon_collage(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Сетка 2×2 — «Коллаж»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(*Palette.ICON_NEUTRAL), 2))
    m = Metrics.ICON_MARGIN_SMALL
    # Внешняя рамка
    p.drawRect(m, m, size - 2 * m, size - 2 * m)
    # Разделители
    cx = size // 2
    cy = size // 2
    p.drawLine(cx, m, cx, size - m)
    p.drawLine(m, cy, size - m, cy)
    p.end()
    return QIcon(pm)


def make_icon_series(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Две перекрывающиеся рамки — «Серия»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(*Palette.ICON_SERIES_BACK), 2)
    p.setPen(pen)
    m = Metrics.ICON_MARGIN_SERIES
    offset = Metrics.ICON_SERIES_OFFSET
    # Задняя рамка
    p.drawRoundedRect(m + offset, m, size - 2 * m, size - 2 * m, 6, 6)
    # Передняя рамка
    p.setPen(QPen(QColor(*Palette.ICON_SERIES_FRONT), 2))
    p.drawRoundedRect(m, m + offset, size - 2 * m, size - 2 * m, 6, 6)
    # Индикатор счётчика
    p.setPen(QPen(QColor(*Palette.ICON_SERIES_COUNTER), 2))
    p.drawLine(size // 2 - 3, size - m - 2, size // 2 + 4, size - m - 2)
    p.end()
    return QIcon(pm)


def make_icon_ocr(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Миниатюра «OCR» с рамкой и строками текста."""

    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

    margin = Metrics.ICON_MARGIN_SMALL
    rect_radius = 6

    # Контур сканируемого листа
    frame_pen = QPen(QColor(*Palette.ICON_NEUTRAL), 2)
    p.setPen(frame_pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, rect_radius, rect_radius)

    # Горизонтальные линии текста
    line_pen = QPen(QColor(*Palette.ICON_BASE), 2)
    p.setPen(line_pen)
    gap = (size - 2 * margin) / 4
    for i in range(1, 4):
        y = margin + i * gap
        p.drawLine(margin + 4, y, size - margin - 4, y)

    # Буква Т в центре как символ текста
    p.setPen(QPen(QColor(*Palette.ICON_POSITIVE), 2))
    font = QFont()
    font.setFamily("Montserrat")
    font.setBold(True)
    font.setPointSize(int(size * 0.36))
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "T")
    p.end()

    return QIcon(pm)
