from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
)


def _styled_pen(source_pen: QPen) -> QPen:
    """Return a copy of the pen with rounded caps and joins for a softer look."""
    pen = QPen(source_pen)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


class ModernPathItem(QGraphicsPathItem):
    """Path item that keeps a clean stroke even when selected."""

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(_styled_pen(self.pen()))
        painter.setBrush(self.brush())
        painter.drawPath(self.path())
        painter.restore()


class ModernEllipseItem(QGraphicsEllipseItem):
    """Ellipse item without the default dashed selection outline."""

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(_styled_pen(self.pen()))
        painter.setBrush(self.brush())
        painter.drawEllipse(self.rect())
        painter.restore()


class ModernLineItem(QGraphicsLineItem):
    """Line item with consistent stroke when selected."""

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(_styled_pen(self.pen()))
        painter.drawLine(self.line())
        painter.restore()


class ModernPixmapItem(QGraphicsPixmapItem):
    """Pixmap item that avoids the default highlight frame."""

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        if self.pixmap().isNull():
            return
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.restore()


class ModernItemGroup(QGraphicsItemGroup):
    """Item group that keeps selection visuals external."""

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.restore()
