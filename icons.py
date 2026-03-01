# -*- coding: utf-8 -*-
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
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

def make_icon_ocr_scan(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Сканер текста — «Распознать текст»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    stroke = QPen(QColor(*Palette.ICON_NEUTRAL), 2)
    p.setPen(stroke)
    m = Metrics.ICON_MARGIN_SMALL
    rect_size = size - 2 * m
    p.drawRoundedRect(m, m, rect_size, rect_size, 4, 4)
    p.drawLine(m + 3, m + 5, m + 3, m + rect_size - 5)
    p.drawLine(size - m - 3, m + 5, size - m - 3, m + rect_size - 5)
    p.setPen(QPen(QColor(*Palette.ICON_POSITIVE), 2))
    p.drawText(pm.rect(), Qt.AlignCenter, "OCR")
    p.end()
    return QIcon(pm)

def make_icon_text_mode(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Буква «T» — «Режим текста»"""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(*Palette.ICON_NEUTRAL), 2))
    margin = Metrics.ICON_MARGIN_SMALL
    p.drawLine(margin, margin + 2, size - margin, margin + 2)
    p.drawLine(size // 2, margin + 2, size // 2, size - margin - 3)
    p.setPen(QPen(QColor(*Palette.ICON_POSITIVE), 2))
    p.drawLine(margin + 3, size - margin - 3, size - margin - 3, size - margin - 3)
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


def make_icon_video(size: int = Metrics.ICON_SMALL) -> QIcon:
    """Camera icon for video capture that stays readable on light and dark surfaces."""
    pm = _pm(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    body_fill = QColor(Palette.PRIMARY_LIGHT)
    body_stroke = QColor(Palette.PRIMARY_HOVER)
    lens_fill = QColor(Palette.PRIMARY)
    rec_dot = QColor(Palette.ERROR)

    m = Metrics.ICON_MARGIN_SMALL
    body_w = size - (2 * m) - 6
    body_h = max(8, size - (2 * m) - 4)
    body_y = (size - body_h) // 2

    p.setPen(QPen(body_stroke, 1.8))
    p.setBrush(body_fill)
    p.drawRoundedRect(m, body_y, body_w, body_h, 4, 4)

    lens_x = m + body_w + 1
    p.setPen(QPen(body_stroke, 1.6))
    p.setBrush(lens_fill)
    p.drawRect(lens_x, body_y + 3, max(2, size - m - lens_x), max(4, body_h - 6))
    p.drawLine(lens_x, body_y + 3, size - m, body_y + 1)
    p.drawLine(lens_x, body_y + body_h - 3, size - m, body_y + body_h - 1)
    p.drawLine(size - m, body_y + 1, size - m, body_y + body_h - 1)

    dot_r = 3 if size >= 28 else 2
    dot_x = m + body_w // 2 - dot_r
    dot_y = body_y + body_h // 2 - dot_r
    p.setPen(QPen(QColor("#ffffff"), 1))
    p.setBrush(rec_dot)
    p.drawEllipse(dot_x, dot_y, dot_r * 2 + 1, dot_r * 2 + 1)
    p.end()
    return QIcon(pm)