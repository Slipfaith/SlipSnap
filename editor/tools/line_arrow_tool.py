# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF, QLineF
from PySide6.QtWidgets import QGraphicsItem

from .base_tool import BaseTool
from editor.undo_commands import AddCommand
from editor.ui.selection_items import ModernItemGroup, ModernLineItem


class LineTool(BaseTool):
    """Draws straight lines."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._start = None
        self._tmp = None

    def press(self, pos: QPointF):
        self._start = pos
        self._tmp = None

    def move(self, pos: QPointF):
        if self._tmp is None:
            self._tmp = ModernLineItem(QLineF(self._start, pos))
            self._tmp.setPen(self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.canvas.scene.addItem(self._tmp)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
            self.canvas.bring_to_front(self._tmp, record=False)
        else:
            self._tmp.setLine(QLineF(self._start, pos))

    def release(self, pos: QPointF):  # noqa: D401
        self._tmp = None


class ArrowTool(BaseTool):
    """Draws arrows."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._start = None
        self._tmp = None

    def press(self, pos: QPointF):
        self._start = pos
        self._tmp = None

    def move(self, pos: QPointF):
        if self._tmp is None:
            self._tmp = self._create_arrow_group(self._start, pos)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.canvas.bring_to_front(self._tmp, record=False)
        else:
            self.canvas.scene.removeItem(self._tmp)
            self._tmp = self._create_arrow_group(self._start, pos)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def release(self, pos: QPointF):  # noqa: D401
        if self._tmp is not None:
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
            self.canvas.bring_to_front(self._tmp, record=False)
            self._tmp = None

    def _create_arrow_group(self, start: QPointF, end: QPointF):
        group = ModernItemGroup()
        line = ModernLineItem(QLineF(start, end))
        line.setPen(self.canvas._pen)
        self.canvas.scene.addItem(line)
        group.addToGroup(line)

        v = end - start
        length = (v.x() ** 2 + v.y() ** 2) ** 0.5
        if length >= 1:
            ux, uy = v.x() / length, v.y() / length
            head = 12
            left = QPointF(
                end.x() - ux * head - uy * head * 0.5,
                end.y() - uy * head + ux * head * 0.5,
            )
            right = QPointF(
                end.x() - ux * head + uy * head * 0.5,
                end.y() - uy * head - ux * head * 0.5,
            )
            left_line = ModernLineItem(QLineF(end, left))
            left_line.setPen(self.canvas._pen)
            right_line = ModernLineItem(QLineF(end, right))
            right_line.setPen(self.canvas._pen)
            self.canvas.scene.addItem(left_line)
            self.canvas.scene.addItem(right_line)
            group.addToGroup(left_line)
            group.addToGroup(right_line)

        group.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.canvas.scene.addItem(group)
        return group