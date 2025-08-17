from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem


class AddCommand(QUndoCommand):
    """Command to add an item to the scene."""

    def __init__(self, scene: QGraphicsScene, item: QGraphicsItem):
        super().__init__("Добавить")
        self.scene = scene
        self.item = item

    def undo(self):
        self.scene.removeItem(self.item)

    def redo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)


class RemoveCommand(QUndoCommand):
    """Command to remove an item from the scene."""

    def __init__(self, scene: QGraphicsScene, item: QGraphicsItem):
        super().__init__("Удалить")
        self.scene = scene
        self.item = item

    def undo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)

    def redo(self):
        self.scene.removeItem(self.item)


class MoveCommand(QUndoCommand):
    """Command to move items between positions."""

    def __init__(self, items_pos):
        # items_pos: Dict[QGraphicsItem, Tuple[QPointF, QPointF]]
        super().__init__("Переместить")
        self.items_pos = items_pos

    def undo(self):
        for item, (old, new) in self.items_pos.items():
            item.setPos(old)

    def redo(self):
        for item, (old, new) in self.items_pos.items():
            item.setPos(new)


class ScaleCommand(QUndoCommand):
    """Command to scale items."""

    def __init__(self, items_scale):
        # items_scale: Dict[QGraphicsItem, Tuple[float, float]]
        super().__init__("Масштабировать")
        self.items_scale = items_scale

    def undo(self):
        for item, (old, new) in self.items_scale.items():
            item.setScale(old)

    def redo(self):
        for item, (old, new) in self.items_scale.items():
            item.setScale(new)
