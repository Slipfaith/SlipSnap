from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem
from PIL import ImageFilter

from logic import pil_to_qpixmap, qimage_to_pil
from .base_tool import BaseTool
from editor.undo_commands import AddCommand


class BlurTool(BaseTool):
    """Tool for blurring rectangular regions."""

    def __init__(self, canvas, preview_color):
        super().__init__(canvas)
        self._start = None
        self._tmp = None
        self.preview_color = preview_color

    def press(self, pos: QPointF):
        self._start = pos
        self._tmp = None

    def move(self, pos: QPointF):
        if self._tmp is None:
            pen = QPen(Qt.DashLine)
            pen.setColor(QColor(self.preview_color))
            self._tmp = self.canvas.scene.addRect(QRectF(self._start, pos).normalized(), pen)
        else:
            self._tmp.setRect(QRectF(self._start, pos).normalized())

    def release(self, pos: QPointF):
        if self._tmp is not None:
            rect = self._tmp.rect()
            self.canvas.scene.removeItem(self._tmp)
            self._tmp = None
            if rect.width() > 1 and rect.height() > 1:
                item = self._create_blur_item(rect)
                if item:
                    self.canvas.undo_stack.push(AddCommand(self.canvas.scene, item))

    def _create_blur_item(self, rect: QRectF):
        r = rect.toRect()
        if r.isNull():
            return None
        base = self.canvas.pixmap_item.pixmap().copy(r)
        qimg = base.toImage()
        pil_img = qimage_to_pil(qimg)
        pil_blur = pil_img.filter(ImageFilter.GaussianBlur(12))
        pix = pil_to_qpixmap(pil_blur)
        item = QGraphicsPixmapItem(pix)
        item.setPos(rect.left(), rect.top())
        item.setZValue(1)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.canvas.scene.addItem(item)
        return item
