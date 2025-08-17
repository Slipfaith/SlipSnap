from PySide6.QtCore import QPointF, QLineF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsItemGroup

from .base_tool import BaseTool
from editor.undo_commands import AddCommand


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
            self._tmp = self.canvas.scene.addLine(QLineF(self._start, pos), self.canvas._pen)
            self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
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
        else:
            self.canvas.scene.removeItem(self._tmp)
            self._tmp = self._create_arrow_group(self._start, pos)
            self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def release(self, pos: QPointF):  # noqa: D401
        if self._tmp is not None:
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._tmp))
            self._tmp = None

    def _create_arrow_group(self, start: QPointF, end: QPointF):
        group = QGraphicsItemGroup()
        line = self.canvas.scene.addLine(QLineF(start, end), self.canvas._pen)
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
            left_line = self.canvas.scene.addLine(QLineF(end, left), self.canvas._pen)
            right_line = self.canvas.scene.addLine(QLineF(end, right), self.canvas._pen)
            group.addToGroup(left_line)
            group.addToGroup(right_line)

        group.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.canvas.scene.addItem(group)
        return group
