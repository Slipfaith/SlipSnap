from PySide6.QtCore import QPointF, QLineF
from PySide6.QtWidgets import QGraphicsItem

from .base_tool import BaseTool
from editor.undo_commands import AddCommand


class PencilTool(BaseTool):
    """Freehand drawing tool."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._last_point = None
        self._drawing = False

    def press(self, pos: QPointF):
        self._last_point = pos
        self._drawing = False

    def move(self, pos: QPointF):
        if self._last_point is not None:
            if not self._drawing:
                # Start a macro so the whole stroke becomes a single undo step
                self.canvas.undo_stack.beginMacro("Карандаш")
                self._drawing = True
            line = self.canvas.scene.addLine(QLineF(self._last_point, pos), self.canvas._pen)
            line.setFlag(QGraphicsItem.ItemIsSelectable, True)
            line.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, line))
            self._last_point = pos

    def release(self, pos: QPointF):  # noqa: D401 - docs inherited
        self._last_point = None
        if self._drawing:
            # Finish the macro when the stroke ends
            self.canvas.undo_stack.endMacro()
            self._drawing = False
