from PySide6.QtCore import QPointF, Qt, QRectF, QLineF
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QPixmap, QPainter
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QWidget,
    QSlider,
    QVBoxLayout,
    QLabel,
)

from .base_tool import BaseTool
from editor.undo_commands import RemoveCommand
from editor.ui.styles import ModernColors


class EraserTool(BaseTool):

    def __init__(self, canvas):
        super().__init__(canvas)
        self.eraser_size = 20
        self.min_size = 5
        self.max_size = 100
        self.size_step = 5
        self._last_pos = None
        self._last_item = None
        self._create_cursor()

    def press(self, pos: QPointF):
        self._last_pos = pos
        self._last_item = None
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
            color = QColor(255, 80, 80, alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))

            painter.drawEllipse(
                center - blur_radius,
                center - blur_radius,
                blur_radius * 2,
                blur_radius * 2
            )

        # Основной круг
        main_color = QColor(255, 100, 100, 120)
        painter.setBrush(QBrush(main_color))
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)

        # Центральная точка для точности
        painter.setPen(QPen(QColor(255, 50, 50, 180), 2))
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

        items_to_remove = []
        blur_found = False
        for item in self.canvas.scene.items(erase_rect):
            if item is self.canvas.pixmap_item:
                continue
            if item.data(0) == "blur":
                self._erase_blur_item(item, pos)
                blur_found = True
                continue
            if self._item_intersects_circle(item, pos, self.eraser_size / 2):
                items_to_remove.append(item)

        for item in items_to_remove:
            self.canvas.scene.removeItem(item)
            self.canvas.undo_stack.push(RemoveCommand(self.canvas.scene, item))

        if not blur_found:
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

    def _erase_blur_item(self, item, pos: QPointF):
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
        super().__init__(flags=Qt.Popup)
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
