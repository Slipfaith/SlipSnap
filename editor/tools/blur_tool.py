from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem
from PIL import ImageFilter, ImageDraw, Image

from logic import pil_to_qpixmap, qimage_to_pil
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

        result = self._generate_blur_pixmap(rect)
        if result is None:
            if self._preview_item is not None:
                self.canvas.scene.removeItem(self._preview_item)
                self._preview_item = None
        else:
            pix, pos = result
            if self._preview_item is None:
                self._preview_item = self.canvas.scene.addPixmap(pix)
                self._preview_item.setZValue(1)
            else:
                self._preview_item.setPixmap(pix)
            self._preview_item.setPos(pos)

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
        img_rect = self.canvas.pixmap_item.boundingRect()
        img_rect = self.canvas.pixmap_item.mapRectToScene(img_rect)
        rect = rect.intersected(img_rect)
        if rect.isNull() or rect.isEmpty():
            return None

        radius = self.blur_radius

        # expand source rect so blur has neighboring pixels to sample from
        expanded = rect.adjusted(-radius, -radius, radius, radius)
        expanded = expanded.intersected(img_rect)
        er = expanded.toRect()
        ex, ey, ew, eh = er.x(), er.y(), er.width(), er.height()

        img = QImage(ew, eh, QImage.Format_RGBA8888)
        img.fill(Qt.transparent)
        p = QPainter(img)
        if self._preview_item is not None:
            self._preview_item.hide()
        self.canvas.scene.render(p, QRectF(0, 0, ew, eh), expanded)
        p.end()
        if self._preview_item is not None:
            self._preview_item.show()
        pil_img = qimage_to_pil(img)

        def _pad_with_edge(image: Image.Image, pad: int) -> Image.Image:
            if pad <= 0:
                return image
            w, h = image.size
            padded = Image.new(image.mode, (w + pad * 2, h + pad * 2))
            padded.paste(image, (pad, pad))
            # edges
            padded.paste(image.crop((0, 0, w, 1)).resize((w, pad)), (pad, 0))
            padded.paste(image.crop((0, h - 1, w, h)).resize((w, pad)), (pad, h + pad))
            padded.paste(image.crop((0, 0, 1, h)).resize((pad, h)), (0, pad))
            padded.paste(image.crop((w - 1, 0, w, h)).resize((pad, h)), (w + pad, pad))
            # corners
            tl = Image.new(image.mode, (pad, pad), image.getpixel((0, 0)))
            tr = Image.new(image.mode, (pad, pad), image.getpixel((w - 1, 0)))
            bl = Image.new(image.mode, (pad, pad), image.getpixel((0, h - 1)))
            br = Image.new(image.mode, (pad, pad), image.getpixel((w - 1, h - 1)))
            padded.paste(tl, (0, 0))
            padded.paste(tr, (w + pad, 0))
            padded.paste(bl, (0, h + pad))
            padded.paste(br, (w + pad, h + pad))
            return padded

        pil_img = _pad_with_edge(pil_img, radius)
        pil_blur = pil_img.filter(ImageFilter.GaussianBlur(radius))

        # crop to original rect inside the padded/expanded image
        crop_x = radius + int(rect.left() - expanded.left())
        crop_y = radius + int(rect.top() - expanded.top())
        crop_w = int(rect.width())
        crop_h = int(rect.height())
        pil_blur = pil_blur.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

        edge = min(self.edge_width, crop_w // 2, crop_h // 2)
        if edge > 0:
            mask = Image.new("L", (crop_w, crop_h), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle((edge, edge, crop_w - edge, crop_h - edge), radius=edge, fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(edge))
            pil_blur.putalpha(mask)

        return pil_to_qpixmap(pil_blur), rect.topLeft()

    def _create_blur_item(self, rect: QRectF):
        result = self._generate_blur_pixmap(rect)
        if result is None:
            return None
        pix, pos = result
        item = QGraphicsPixmapItem(pix)
        item.setPos(pos)
        item.setZValue(1)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        item.setData(0, "blur")
        self.canvas.scene.addItem(item)
        return item
