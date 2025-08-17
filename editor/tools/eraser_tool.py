from PySide6.QtCore import QPointF

from .base_tool import BaseTool


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
            try:
                self.canvas._undo.remove(item)
            except ValueError:
                pass
            break
