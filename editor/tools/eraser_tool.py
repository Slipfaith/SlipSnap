from PySide6.QtCore import QPointF, Qt, QRectF, QLineF
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QPixmap, QPainter, QImage, QUndoCommand
from PySide6.QtWidgets import (
    QWidget,
    QSlider,
    QVBoxLayout,
    QLabel,
    QGraphicsPixmapItem,
    QGraphicsItem,
    QStyleOptionGraphicsItem,
)

from .base_tool import BaseTool
from editor.undo_commands import AddCommand, RemoveCommand
from editor.ui.styles import ModernColors

from design_tokens import Palette, Metrics


class EraserTool(BaseTool):

    def __init__(self, canvas):
        super().__init__(canvas)
        self.eraser_size = Metrics.ERASER_DEFAULT_SIZE
        self.min_size = Metrics.ERASER_MIN_SIZE
        self.max_size = Metrics.ERASER_MAX_SIZE
        self.size_step = Metrics.ERASER_STEP
        self._last_pos = None
        self._last_item = None
        self._pending_erase = {}
        self._create_cursor()

    def press(self, pos: QPointF):
        self._last_pos = pos
        self._last_item = None
        self._pending_erase = {}
        self._erase_at_position(pos)

    def move(self, pos: QPointF):
        if self._last_pos is None:
            self._erase_at_position(pos)
            self._last_pos = pos
        else:
            self._erase_line(self._last_pos, pos)
            self._last_pos = pos

    def release(self, pos: QPointF):
        self._last_pos = None
        self._last_item = None
        if self._pending_erase:
            changes = []
            for item, before in list(self._pending_erase.items()):
                if item is None:
                    continue
                try:
                    after = QPixmap(item.pixmap())
                except Exception:
                    continue
                changes.append((item, before, after))
            if changes:
                self.canvas.undo_stack.push(_EraseCommand(changes))
        self._pending_erase = {}

    def wheel_event(self, delta: int, pos: QPointF):
        if delta > 0:
            self._increase_size()
        else:
            self._decrease_size()

    def key_press(self, key):
        pass

    def _create_cursor(self):
        # Увеличиваем размер для эффекта размытия
        cursor_size = max(32, self.eraser_size + 16)
        pixmap = QPixmap(cursor_size, cursor_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = cursor_size // 2
        radius = self.eraser_size // 2

        # Создаем эффект размытия с несколькими кругами разной прозрачности
        blur_steps = 4
        for i in range(blur_steps, 0, -1):
            alpha = int(80 / i)  # Уменьшающаяся прозрачность
            blur_radius = radius + (i * 2)  # Увеличивающийся радиус

            # Красноватый цвет для ластика
            color = QColor(*Palette.TEXT_TOOL_COLOR)
            color.setAlpha(alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))

            painter.drawEllipse(
                center - blur_radius,
                center - blur_radius,
                blur_radius * 2,
                blur_radius * 2
            )

        # Основной круг
        main_color = QColor(*Palette.ERASER_MAIN_COLOR)
        painter.setBrush(QBrush(main_color))
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)

        # Центральная точка для точности
        painter.setPen(QPen(QColor(*Palette.ERASER_CENTER_COLOR), 2))
        painter.drawPoint(center, center)

        painter.end()

        self.cursor = QCursor(pixmap, center, center)

        # Устанавливаем курсор сразу, если инструмент активен
        if hasattr(self.canvas, '_tool') and self.canvas._tool == "erase":
            self.canvas.viewport().setCursor(self.cursor)

    def _erase_at_position(self, pos: QPointF):
        erase_rect = QRectF(
            pos.x() - self.eraser_size / 2,
            pos.y() - self.eraser_size / 2,
            self.eraser_size,
            self.eraser_size
        )

        handled = False
        for item in self.canvas.scene.items(erase_rect):
            if isinstance(item, QGraphicsPixmapItem) and item.data(0) == "screenshot":
                continue
            if isinstance(item, QGraphicsPixmapItem):
                self._erase_pixmap_item(item, pos)
                handled = True
                continue
            if self._item_intersects_circle(item, pos, self.eraser_size / 2):
                pix_item = self._vector_item_to_pixmap(item)
                self._erase_pixmap_item(pix_item, pos)
                handled = True
        if not handled:
            self._last_item = None

    def _erase_line(self, start: QPointF, end: QPointF):
        line = QLineF(start, end)
        length = line.length()
        if length == 0:
            self._erase_at_position(end)
            return
        step = max(1.0, self.eraser_size / 2)
        steps = max(1, int(length / step))
        for i in range(1, steps + 1):
            point = line.pointAt(i / steps)
            self._erase_at_position(point)
            self._last_pos = point

    def _vector_item_to_pixmap(self, item):
        rect = item.boundingRect()
        w = max(1, int(rect.width()))
        h = max(1, int(rect.height()))
        image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(-rect.topLeft())
        option = QStyleOptionGraphicsItem()
        item.paint(painter, option, None)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        pix_item = QGraphicsPixmapItem(pixmap)
        pix_item.setPos(item.mapToScene(rect.topLeft()))
        pix_item.setZValue(item.zValue())
        pix_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        pix_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.canvas.scene.addItem(pix_item)
        self.canvas.scene.removeItem(item)
        self.canvas.undo_stack.push(RemoveCommand(self.canvas.scene, item))
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, pix_item))
        return pix_item

    def _erase_pixmap_item(self, item, pos: QPointF):
        if item not in self._pending_erase:
            self._pending_erase[item] = QPixmap(item.pixmap())
        pix = item.pixmap()
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        local = item.mapFromScene(pos)
        if self._last_pos is not None and self._last_item is item:
            prev_local = item.mapFromScene(self._last_pos)
            pen = QPen(Qt.GlobalColor.transparent, self.eraser_size,
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(prev_local, local)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.GlobalColor.transparent)
            r = self.eraser_size / 2
            painter.drawEllipse(local, r, r)
        painter.end()
        item.setPixmap(pix)
        self._last_pos = pos
        self._last_item = item

    def _item_intersects_circle(self, item, center: QPointF, radius: float) -> bool:
        item_rect = item.boundingRect()
        item_center = item.mapToScene(item_rect.center())

        distance = ((item_center.x() - center.x()) ** 2 +
                    (item_center.y() - center.y()) ** 2) ** 0.5

        item_radius = max(item_rect.width(), item_rect.height()) / 2

        return distance <= radius + item_radius

    def _increase_size(self):
        if self.eraser_size < self.max_size:
            self.eraser_size = min(self.max_size, self.eraser_size + self.size_step)
            self._create_cursor()

    def _decrease_size(self):
        if self.eraser_size > self.min_size:
            self.eraser_size = max(self.min_size, self.eraser_size - self.size_step)
            self._create_cursor()

    def get_size(self) -> int:
        return self.eraser_size

    def set_size(self, size: int):
        self.eraser_size = max(self.min_size, min(self.max_size, size))
        self._create_cursor()

    def show_size_popup(self, global_pos):
        if not hasattr(self, "_popup") or self._popup is None:
            self._popup = _EraserSizePopup(self)
        self._popup.slider.setValue(self.get_size())
        self._popup.move(global_pos)
        self._popup.show()


class _EraserSizePopup(QWidget):
    def __init__(self, tool: EraserTool):
        super().__init__()
        self.setWindowFlags(Qt.Popup)
        self.tool = tool
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(tool.min_size, tool.max_size)
        self.slider.setValue(tool.get_size())
        self.label = QLabel(f"{tool.get_size()} px")
        self.label.setAlignment(Qt.AlignCenter)
        self.slider.valueChanged.connect(self._on_value_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        self.setStyleSheet(
            f"""
            QWidget {{
                background: {ModernColors.SURFACE};
                border: 1px solid {ModernColors.BORDER};
                border-radius: 8px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {ModernColors.BORDER};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                height: 12px;
                background: {ModernColors.PRIMARY};
                border-radius: 6px;
            }}
            QLabel {{
                color: {ModernColors.TEXT_PRIMARY};
            }}
            """
        )

    def _on_value_changed(self, value: int):
        self.label.setText(f"{value} px")
        self.tool.set_size(value)


class _EraseCommand(QUndoCommand):
    """Undo command for eraser changes to pixmap items."""

    def __init__(self, changes):
        super().__init__("Erase")
        self._changes = changes

    def undo(self):
        for item, before, _after in self._changes:
            if item is None:
                continue
            try:
                item.setPixmap(before)
            except Exception:
                continue

    def redo(self):
        for item, _before, after in self._changes:
            if item is None:
                continue
            try:
                item.setPixmap(after)
            except Exception:
                continue
