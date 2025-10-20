from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from .base_tool import BaseTool
from editor.undo_commands import AddCommand


class PencilTool(BaseTool):
    """Freehand drawing tool."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._path = None
        self._path_item = None

    def press(self, pos: QPointF):
        self._path = QPainterPath(pos)
        self._path_item = QGraphicsPathItem(self._path)
        self._path_item.setPen(self.canvas._pen)
        self._path_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self._path_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.canvas.scene.addItem(self._path_item)

    def move(self, pos: QPointF):
        if self._path is not None and self._path_item is not None:
            self._path.lineTo(pos)
            self._path_item.setPath(self._path)

    def release(self, pos: QPointF):  # noqa: D401 - docs inherited
        if self._path_item is not None:
            # If the user just clicked without moving, create a dot
            if self._path.elementCount() == 1:
                self._path.lineTo(pos)
                self._path_item.setPath(self._path)
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, self._path_item))
            # Bring the new drawing to the front automatically
            self.canvas.bring_to_front(self._path_item, record=False)
            self._path = None
            self._path_item = None
