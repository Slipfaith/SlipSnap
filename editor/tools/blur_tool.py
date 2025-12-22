from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem
from PIL import ImageFilter, ImageDraw, Image

from logic import pil_to_qpixmap, qimage_to_pil
from .base_tool import BaseTool
from editor.undo_commands import AddCommand
from editor.ui.selection_items import ModernPixmapItem


class BlurTool(BaseTool):
    """Tool for blurring rectangular regions."""

    def __init__(self, canvas, preview_color):
        super().__init__(canvas)
        self._start = None
        self._rect_item = None
        self._preview_item = None
        self.preview_color = preview_color
        self.blur_radius = 5
        self.edge_width = 2

    def _image_rect(self) -> QRectF:
        """Combined bounding rect of all screenshot items."""
        items = [
            it
            for it in self.canvas.scene.items()
            if isinstance(it, QGraphicsPixmapItem) and it.data(0) != "blur"
        ]
        if not items:
            return QRectF()
        rect = items[0].sceneBoundingRect()
        for it in items[1:]:
            rect = rect.united(it.sceneBoundingRect())
        return rect

    def press(self, pos: QPointF):
        self._start = pos
        if self._rect_item is not None:
            self.canvas.scene.removeItem(self._rect_item)
            self._rect_item = None
        if self._preview_item is not None:
            self.canvas.scene.removeItem(self._preview_item)
            self._preview_item = None

    def move(self, pos: QPointF):
        user_rect = QRectF(self._start, pos).normalized()

        img_rect = self._image_rect()

        clipped_rect = user_rect.intersected(img_rect)

        if self._rect_item is None:
            pen = QPen(QColor(self.preview_color))
            pen.setCosmetic(True)
            pen.setWidthF(2.0)
            pen.setStyle(Qt.SolidLine)
            self._rect_item = self.canvas.scene.addRect(clipped_rect, pen)
        else:
            self._rect_item.setRect(clipped_rect)

        result = self._generate_blur_pixmap(clipped_rect)
        if result is None:
            if self._preview_item is not None:
                self.canvas.scene.removeItem(self._preview_item)
                self._preview_item = None
        else:
            pix, pos = result
            if self._preview_item is None:
                self._preview_item = self.canvas.scene.addPixmap(pix)
            else:
                self._preview_item.setPixmap(pix)
            max_z = max(
                (it.zValue() for it in self.canvas.scene.items() if it is not self._preview_item),
                default=0,
            )
            self._preview_item.setZValue(max_z + 1)
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
                    self.canvas.bring_to_front(item, record=False)

    def _generate_blur_pixmap(self, rect: QRectF):
        img_rect = self._image_rect().toAlignedRect()

        rect = rect.intersected(img_rect).toAlignedRect()
        if rect.isNull() or rect.isEmpty():
            return None

        radius = int(self.blur_radius)

        expanded = rect.adjusted(-radius, -radius, radius, radius)
        expanded = expanded.intersected(img_rect)
        ex, ey, ew, eh = expanded.x(), expanded.y(), expanded.width(), expanded.height()

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
            padded.paste(image.crop((0, 0, w, 1)).resize((w, pad)), (pad, 0))
            padded.paste(image.crop((0, h - 1, w, h)).resize((w, pad)), (pad, h + pad))
            padded.paste(image.crop((0, 0, 1, h)).resize((pad, h)), (0, pad))
            padded.paste(image.crop((w - 1, 0, w, h)).resize((pad, h)), (w + pad, pad))
            tl = Image.new(image.mode, (pad, pad), image.getpixel((0, 0)))
            tr = Image.new(image.mode, (pad, pad), image.getpixel((w - 1, 0)))
            bl = Image.new(image.mode, (pad, pad), image.getpixel((0, h - 1)))
            br = Image.new(image.mode, (pad, pad), image.getpixel((w - 1, h - 1)))
            padded.paste(tl, (0, 0))
            padded.paste(tr, (w + pad, 0))
            padded.paste(bl, (0, h + pad))
            padded.paste(br, (w + pad, h + pad))
            return padded

        original_alpha = pil_img.getchannel('A') if pil_img.mode == 'RGBA' else None

        pil_img = _pad_with_edge(pil_img, radius)
        pil_blur = pil_img.filter(ImageFilter.GaussianBlur(radius))

        crop_x = radius + rect.left() - expanded.left()
        crop_y = radius + rect.top() - expanded.top()
        crop_w = rect.width()
        crop_h = rect.height()
        pil_blur = pil_blur.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

        if original_alpha:
            original_alpha_padded = _pad_with_edge(original_alpha, radius)
            original_alpha_cropped = original_alpha_padded.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

            edge = min(self.edge_width, crop_w // 2, crop_h // 2)
            if edge > 0:
                mask = Image.new("L", (crop_w, crop_h), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((edge, edge, crop_w - edge, crop_h - edge), radius=edge, fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(edge))

                from PIL import ImageChops
                final_alpha = ImageChops.darker(original_alpha_cropped, mask)
                pil_blur.putalpha(final_alpha)
            else:
                pil_blur.putalpha(original_alpha_cropped)
        else:
            edge = min(self.edge_width, crop_w // 2, crop_h // 2)
            if edge > 0:
                mask = Image.new("L", (crop_w, crop_h), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((edge, edge, crop_w - edge, crop_h - edge), radius=edge, fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(edge))
                pil_blur.putalpha(mask)

        return pil_to_qpixmap(pil_blur), QPointF(rect.topLeft())

    def _create_blur_item(self, rect: QRectF):
        result = self._generate_blur_pixmap(rect)
        if result is None:
            return None
        pix, pos = result
        item = ModernPixmapItem(pix)
        item.setPos(pos)
        item.setZValue(1)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        item.setData(0, "blur")
        self.canvas.scene.addItem(item)
        return item
