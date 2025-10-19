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

    def __init__(
        self,
        scene: QGraphicsScene,
        item: QGraphicsItem,
        *,
        on_removed=None,
        on_restored=None,
    ):
        super().__init__("Удалить")
        self.scene = scene
        self.item = item
        self._on_removed = on_removed
        self._on_restored = on_restored

    def undo(self):
        if self.item.scene() is None:
            self.scene.addItem(self.item)
            if self._on_restored is not None:
                self._on_restored(self.item)

    def redo(self):
        self.scene.removeItem(self.item)
        if self._on_removed is not None:
            self._on_removed(self.item)


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


class ZValueCommand(QUndoCommand):
    """Command to change Z-order of items."""

    def __init__(self, items_z):
        # items_z: Dict[QGraphicsItem, Tuple[float, float]]
        super().__init__("Порядок")
        self.items_z = items_z

    def undo(self):
        for item, (old, new) in self.items_z.items():
            item.setZValue(old)

    def redo(self):
        for item, (old, new) in self.items_z.items():
            item.setZValue(new)
