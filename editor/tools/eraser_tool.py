from PySide6.QtCore import QPointF

from .base_tool import BaseTool
from editor.undo_commands import RemoveCommand


class EraserTool(BaseTool):
    """Removes top items at the cursor position."""

    def press(self, pos: QPointF):
        self._erase(pos)

    def move(self, pos: QPointF):
        self._erase(pos)

    def release(self, pos: QPointF):  # noqa: D401
        pass

    def _erase(self, pos: QPointF):
        for item in self.canvas.scene.items(pos):
            if item is self.canvas.pixmap_item:
                continue
            self.canvas.scene.removeItem(item)
            self.canvas.undo_stack.push(RemoveCommand(self.canvas.scene, item))
            break
