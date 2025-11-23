from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QPixmap, QIcon, QColor, QCursor,
    QBrush, QLinearGradient, QPainterPath, QRadialGradient,
    QPolygonF
)

from .styles import ModernColors
from design_tokens import Metrics

ICON_SIZE = Metrics.TOOL_ICON

def _base_pixmap() -> QPixmap:
    pm = QPixmap(ICON_SIZE, ICON_SIZE)
    pm.fill(Qt.transparent)
    return pm

def make_icon_rect() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    rect = QRectF(6, 8, 28, 24)

    # Fill with subtle primary color
    c_fill = QColor(ModernColors.PRIMARY)
    c_fill.setAlpha(40)
    p.setBrush(c_fill)

    # Stroke
    pen = QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)

    p.drawRoundedRect(rect, 4, 4)

    # Add small corner indicators
    p.setBrush(QColor(ModernColors.PRIMARY))
    p.setPen(Qt.NoPen)
    r = 3
    p.drawEllipse(rect.topLeft(), r/2, r/2)
    p.drawEllipse(rect.bottomRight(), r/2, r/2)

    p.end()
    return QIcon(pm)

def make_icon_ellipse() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    rect = QRectF(6, 8, 28, 24)

    c_fill = QColor(ModernColors.PRIMARY)
    c_fill.setAlpha(40)
    p.setBrush(c_fill)

    pen = QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5)
    p.setPen(pen)

    p.drawEllipse(rect)
    p.end()
    return QIcon(pm)

def make_icon_line() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    pen = QPen(QColor(ModernColors.TEXT_SECONDARY), 3, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(8, 32, 32, 8)

    # Endpoints
    p.setBrush(QColor(ModernColors.PRIMARY))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(8, 32), 2.5, 2.5)
    p.drawEllipse(QPointF(32, 8), 2.5, 2.5)

    p.end()
    return QIcon(pm)

def make_icon_arrow() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    color = QColor(ModernColors.TEXT_SECONDARY)
    pen = QPen(color, 3, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)

    # Shaft
    start = QPointF(8, 32)
    end = QPointF(28, 12)
    p.drawLine(start, end)

    # Head
    path = QPainterPath()
    path.moveTo(end)
    path.lineTo(20, 12) # Wing 1
    path.lineTo(28, 12) # Tip
    path.lineTo(28, 20) # Wing 2

    # Fill head slightly
    pen = QPen(color, 3)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)

    p.end()
    return QIcon(pm)

def make_icon_pencil() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Pencil body transformation
    p.translate(20, 20)
    p.rotate(-45)
    p.translate(-20, -20)

    # Pencil body
    body_rect = QRectF(16, 8, 8, 20)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2))
    p.setBrush(QColor(ModernColors.SURFACE))
    p.drawRect(body_rect)

    # Tip
    path = QPainterPath()
    path.moveTo(16, 28)
    path.lineTo(24, 28)
    path.lineTo(20, 34)
    path.closeSubpath()
    p.setBrush(QColor(ModernColors.TEXT_SECONDARY))
    p.drawPath(path)

    # Eraser
    eraser_rect = QRectF(16, 4, 8, 4)
    p.setBrush(QColor(ModernColors.ERROR))
    p.drawRect(eraser_rect)

    p.end()
    return QIcon(pm)

def make_icon_marker() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Marker stroke
    color = QColor(ModernColors.PRIMARY)
    color.setAlpha(180)

    pen = QPen(color, 8, Qt.SolidLine, Qt.FlatCap)
    p.setPen(pen)
    p.drawLine(10, 30, 30, 10)

    # Beveled ends visual trick
    p.setPen(Qt.NoPen)
    p.setBrush(color)

    # Draw angled rects at ends to simulate chisel tip
    p.save()
    p.translate(10, 30)
    p.rotate(-45)
    p.drawRect(0, -4, 2, 8)
    p.restore()

    p.save()
    p.translate(30, 10)
    p.rotate(-45)
    p.drawRect(-2, -4, 2, 8)
    p.restore()

    p.end()
    return QIcon(pm)

def make_icon_text() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2))

    # Draw a serif T manually to ensure look
    path = QPainterPath()
    # Top bar
    path.addRoundedRect(QRectF(8, 8, 24, 5), 2, 2)
    # Stem
    path.addRoundedRect(QRectF(17.5, 10, 5, 22), 2, 2)

    p.fillPath(path, QColor(ModernColors.TEXT_SECONDARY))

    # Cursor indicator
    p.setPen(QPen(QColor(ModernColors.PRIMARY), 2))
    p.drawLine(34, 20, 34, 32)

    p.end()
    return QIcon(pm)

def make_icon_blur() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Create a droplet shape or just a blurry circle
    grad = QRadialGradient(20, 20, 12)
    grad.setColorAt(0, QColor(ModernColors.TEXT_SECONDARY))
    grad.setColorAt(0.7, QColor(ModernColors.TEXT_SECONDARY).lighter(150))
    grad.setColorAt(1, Qt.transparent)

    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawEllipse(8, 8, 24, 24)

    # Add a clear ring to signify tool
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(14, 14, 12, 12)

    p.end()
    return QIcon(pm)

def make_icon_eraser() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Draw a parallelogram block
    path = QPainterPath()
    path.moveTo(14, 10)
    path.lineTo(28, 10)
    path.lineTo(24, 28)
    path.lineTo(10, 28)
    path.closeSubpath()

    # Two-tone eraser
    # White part
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2))
    p.setBrush(QColor(ModernColors.SURFACE))
    p.drawPath(path)

    # Pink part (blue in our theme)
    path2 = QPainterPath()
    path2.moveTo(14, 10)
    path2.lineTo(18, 10)
    path2.lineTo(14, 28)
    path2.lineTo(10, 28)
    path2.closeSubpath()

    p.setBrush(QColor(ModernColors.PRIMARY))
    p.drawPath(path2)

    p.end()
    return QIcon(pm)

def make_icon_select() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Dashed selection box
    pen = QPen(QColor(ModernColors.TEXT_SECONDARY), 2, Qt.DashLine)
    p.setPen(pen)
    p.drawRect(8, 10, 20, 18)

    # Cursor
    cursor_path = QPainterPath()
    cursor_path.moveTo(22, 22)
    cursor_path.lineTo(22, 32)
    cursor_path.lineTo(25, 29)
    cursor_path.lineTo(28, 34) # Leg 1
    cursor_path.lineTo(30, 33) # Leg width
    cursor_path.lineTo(27, 28)
    cursor_path.lineTo(32, 28)
    cursor_path.closeSubpath()

    p.setPen(QPen(QColor(ModernColors.SURFACE), 1))
    p.setBrush(QColor(ModernColors.TEXT_PRIMARY))
    p.drawPath(cursor_path)

    p.end()
    return QIcon(pm)

def make_icon_memes() -> QIcon:
    pm = _base_pixmap()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Happy face
    face_rect = QRectF(6, 6, 28, 28)
    p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2))
    p.setBrush(QColor(ModernColors.SURFACE))
    p.drawEllipse(face_rect)

    # Eyes
    p.setBrush(QColor(ModernColors.TEXT_PRIMARY))
    p.setPen(Qt.NoPen)
    p.drawEllipse(12, 14, 4, 4)
    p.drawEllipse(24, 14, 4, 4)

    # Smile
    p.setPen(QPen(QColor(ModernColors.PRIMARY), 2.5, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(12, 16, 16, 12, 200 * 16, 140 * 16)

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
