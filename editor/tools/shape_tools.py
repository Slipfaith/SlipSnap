# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsItem

from .base_tool import BaseTool
from editor.undo_commands import AddCommand
from editor.ui.selection_items import ModernEllipseItem, ModernPathItem


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
        rect = QRectF(self._start, pos).normalized()
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        if self._tmp is None:
            self._tmp = ModernPathItem(path)
            self._tmp.setPen(self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas.scene.addItem(self._tmp)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
            self.canvas.bring_to_front(self._tmp, record=False)
        else:
            self._tmp.setPath(path)


class EllipseTool(_BaseShapeTool):
    """Draws ellipses."""

    def move(self, pos: QPointF):
        if self._tmp is None:
            self._tmp = ModernEllipseItem(QRectF(self._start, pos).normalized())
            self._tmp.setPen(self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas.scene.addItem(self._tmp)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
            self.canvas.bring_to_front(self._tmp, record=False)
        else:
            self._tmp.setRect(QRectF(self._start, pos).normalized())