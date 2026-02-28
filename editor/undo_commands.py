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


class ResizeCommand(QUndoCommand):
    """Command to scale an item while keeping an anchor corner fixed."""

    def __init__(self, item, old_scale: float, new_scale: float, old_pos, new_pos):
        from PySide6.QtCore import QPointF  # local import to avoid circular
        super().__init__("Изменить размер")
        self.item = item
        self.old_scale = old_scale
        self.new_scale = new_scale
        self.old_pos = old_pos
        self.new_pos = new_pos

    def undo(self):
        self.item.setScale(self.old_scale)
        self.item.setPos(self.old_pos)

    def redo(self):
        self.item.setScale(self.new_scale)
        self.item.setPos(self.new_pos)


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


class RotateCommand(QUndoCommand):
    """Command to rotate an item around its centre."""

    def __init__(self, item, origin, old_rotation: float, new_rotation: float):
        from PySide6.QtCore import QPointF
        super().__init__("Повернуть")
        self.item = item
        self.origin = QPointF(origin)
        self.old_rotation = old_rotation
        self.new_rotation = new_rotation

    def undo(self):
        self.item.setTransformOriginPoint(self.origin)
        self.item.setRotation(self.old_rotation)

    def redo(self):
        self.item.setTransformOriginPoint(self.origin)
        self.item.setRotation(self.new_rotation)
