from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem
from PIL import ImageFilter, ImageDraw, Image

from logic import pil_to_qpixmap
from .base_tool import BaseTool
from editor.undo_commands import AddCommand


class BlurTool(BaseTool):
    """Tool for blurring rectangular regions."""

    def __init__(self, canvas, preview_color):
        super().__init__(canvas)
        self._start = None
        self._rect_item = None  # preview rectangle
        self._preview_item = None  # live blur preview
        self.preview_color = preview_color
        self.blur_radius = 5  # default blur strength increased
        self.edge_width = 2  # minimal softness of edges

    def press(self, pos: QPointF):
        self._start = pos
        if self._rect_item is not None:
            self.canvas.scene.removeItem(self._rect_item)
            self._rect_item = None
        if self._preview_item is not None:
            self.canvas.scene.removeItem(self._preview_item)
            self._preview_item = None

    def move(self, pos: QPointF):
        rect = QRectF(self._start, pos).normalized()
        if self._rect_item is None:
            pen = QPen(Qt.DashLine)
            pen.setColor(QColor(self.preview_color))
            self._rect_item = self.canvas.scene.addRect(rect, pen)
        else:
            self._rect_item.setRect(rect)

        pix = self._generate_blur_pixmap(rect)
        if self._preview_item is None:
            self._preview_item = self.canvas.scene.addPixmap(pix)
            self._preview_item.setZValue(1)
        else:
            self._preview_item.setPixmap(pix)
        self._preview_item.setPos(rect.left(), rect.top())

    def release(self, pos: QPointF):
        if self._rect_item is not None:
            rect = self._rect_item.rect()
            self.canvas.scene.removeItem(self._rect_item)
            self._rect_item = None
            if self._preview_item is not None:
                self.canvas.scene.removeItem(self._preview_item)
                self._preview_item = None
            if rect.width() > 1 and rect.height() > 1:
                item = self._create_blur_item(rect)
                if item:
                    self.canvas.undo_stack.push(AddCommand(self.canvas.scene, item))

    def _generate_blur_pixmap(self, rect: QRectF):
        r = rect.toRect()
        if r.isNull():
            from PySide6.QtGui import QPixmap
            return QPixmap()
        left, top, w, h = r.x(), r.y(), r.width(), r.height()
        pil_img = self.canvas.pil_image.crop((left, top, left + w, top + h))
        pil_blur = pil_img.filter(ImageFilter.GaussianBlur(self.blur_radius))

        edge = min(self.edge_width, w // 2, h // 2)
        if edge > 0:
            mask = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((edge, edge, w - edge, h - edge), radius=edge, fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(edge))
            pil_blur.putalpha(mask)

        return pil_to_qpixmap(pil_blur)

    def _create_blur_item(self, rect: QRectF):
        r = rect.toRect()
        if r.isNull():
            return None
        pix = self._generate_blur_pixmap(rect)
        item = QGraphicsPixmapItem(pix)
        item.setPos(rect.left(), rect.top())
        item.setZValue(1)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        item.setData(0, "blur")
        self.canvas.scene.addItem(item)
        return item
