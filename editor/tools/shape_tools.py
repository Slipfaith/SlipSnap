from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem

from .base_tool import BaseTool


class _BaseShapeTool(BaseTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self._start = None
        self._tmp = None

    def press(self, pos: QPointF):
        self._start = pos
        self._tmp = None

    def release(self, pos: QPointF):  # noqa: D401
        self._tmp = None


class RectangleTool(_BaseShapeTool):
    """Draws rectangles."""

    def move(self, pos: QPointF):
        if self._tmp is None:
            self._tmp = self.canvas.scene.addRect(QRectF(self._start, pos).normalized(), self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas._undo.append(self._tmp)
        else:
            self._tmp.setRect(QRectF(self._start, pos).normalized())


class EllipseTool(_BaseShapeTool):
    """Draws ellipses."""

    def move(self, pos: QPointF):
        if self._tmp is None:
            self._tmp = self.canvas.scene.addEllipse(QRectF(self._start, pos).normalized(), self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas._undo.append(self._tmp)
        else:
            self._tmp.setRect(QRectF(self._start, pos).normalized())
