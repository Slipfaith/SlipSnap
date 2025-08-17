from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen, QPixmap, QIcon, QColor, QCursor, QBrush, QLinearGradient

from .styles import ModernColors

ICON_SIZE = 40


def _base_pixmap() -> QPixmap:
    pm = QPixmap(ICON_SIZE, ICON_SIZE)
    pm.fill(Qt.transparent)
    return pm


def make_icon_rect() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
    p.drawRect(8, 8, 24, 24)
    p.end()
    return QIcon(pm)


def make_icon_ellipse() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
    p.drawEllipse(8, 8, 24, 24)
    p.end()
    return QIcon(pm)


def make_icon_line() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(10, 30, 30, 10)
    p.end()
    return QIcon(pm)


def make_icon_arrow() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(10, 30, 28, 12)
    p.drawLine(28, 12, 23, 15)
    p.drawLine(28, 12, 25, 17)
    p.end()
    return QIcon(pm)


def make_icon_pencil() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
    p.drawLine(10, 30, 30, 10)
    p.setPen(QPen(QColor(ModernColors.PRIMARY), 2.5))
    p.drawEllipse(27, 7, 6, 6)
    p.end()
    return QIcon(pm)


def make_icon_text() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
    f = p.font()
    f.setBold(True)
    f.setPointSize(20)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "T")
    p.end()
    return QIcon(pm)


def make_icon_blur() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(8, 8, 32, 32)
    grad.setColorAt(0, QColor(ModernColors.TEXT_SECONDARY))
    grad.setColorAt(1, QColor(ModernColors.SURFACE))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawEllipse(8, 8, 24, 24)
    p.end()
    return QIcon(pm)


def make_icon_eraser() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
    p.setBrush(QBrush(QColor(ModernColors.TEXT_SECONDARY)))
    p.drawPolygon([
        QPointF(10, 25), QPointF(20, 15), QPointF(30, 25), QPointF(20, 35)
    ])
    p.end()
    return QIcon(pm)


def make_icon_select() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
    p.setBrush(QBrush(QColor(ModernColors.TEXT_SECONDARY)))
    points = [QPointF(10, 10), QPointF(10, 30), QPointF(17, 25), QPointF(25, 30),
              QPointF(30, 25), QPointF(20, 17), QPointF(30, 10)]
    p.drawPolygon(points)
    p.end()
    return QIcon(pm)


def create_pencil_cursor() -> QCursor:
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_PRIMARY), 2.5))
    p.drawLine(4, 19, 19, 4)
    p.setPen(QPen(QColor(ModernColors.PRIMARY), 1.5))
    p.drawEllipse(17, 2, 5, 5)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 1.5))
    p.drawLine(2, 21, 5, 18)
    p.end()
    return QCursor(pm, 4, 19)


def create_select_cursor() -> QCursor:
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ModernColors.TEXT_PRIMARY), 1.8))
    p.setBrush(QBrush(QColor(ModernColors.TEXT_PRIMARY)))
    points = [
        QPointF(3, 3), QPointF(3, 17), QPointF(8, 13),
        QPointF(12, 18), QPointF(15, 16), QPointF(10, 10), QPointF(18, 3)
    ]
    p.drawPolygon(points)
    p.setPen(QPen(QColor(255, 255, 255, 180), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPolygon(points)
    p.end()
    return QCursor(pm, 3, 3)
