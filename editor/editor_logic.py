from io import BytesIO
from pathlib import Path
import struct

from PIL import Image
from PySide6.QtCore import QMimeData, QByteArray
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog

from logic import HISTORY_DIR


def _qimage_to_dib_bytes(qimg: QImage) -> bytes:
    """Convert a QImage to a DIB (BITMAPV5HEADER) byte stream with alpha."""

    if qimg.isNull():
        raise ValueError("QImage is null")

    qimg = qimg.convertToFormat(QImage.Format_ARGB32)
    width = qimg.width()
    height = qimg.height()
    if width == 0 or height == 0:
        return b""

    bytes_per_line = qimg.bytesPerLine()
    img_size = bytes_per_line * height

    ptr = qimg.constBits()
    if hasattr(ptr, "setsize"):
        ptr.setsize(img_size)
        buffer = bytes(ptr)
    else:
        buffer = ptr.tobytes()
        if len(buffer) > img_size:
            buffer = buffer[:img_size]

    header = struct.pack(
        "<IiiHHIIiiIIIII9iIIIIIII",
        124,  # bV5Size
        width,
        -height,  # top-down DIB
        1,  # planes
        32,  # bit count
        3,  # BI_BITFIELDS
        img_size,
        3780,  # ~96 DPI
        3780,  # ~96 DPI
        0,  # clr used
        0,  # clr important
        0x00FF0000,  # red mask
        0x0000FF00,  # green mask
        0x000000FF,  # blue mask
        0xFF000000,  # alpha mask
        0x57696E20,  # LCS_WINDOWS_COLOR_SPACE
        0, 0, 0, 0, 0, 0, 0, 0, 0,  # CIEXYZ endpoints
        0,  # gamma red
        0,  # gamma green
        0,  # gamma blue
        4,  # LCS_GM_IMAGES
        0,  # profile data
        0,  # profile size
        0,  # reserved
    )

    return header + buffer


class EditorLogic:
    def __init__(self, canvas, live_manager):
        self.canvas = canvas
        self.live_manager = live_manager

    def export_image(self) -> Image.Image:
        return self.canvas.export_image()

    def copy_to_clipboard(self):
        if self.canvas.scene.selectedItems():
            img = self.canvas.export_selection()
        else:
            img = self.export_image()
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        data = buffer.getvalue()
        qimg = QImage.fromData(data, "PNG")
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

        bmp_bytes = _qimage_to_dib_bytes(qimg)

        mime = QMimeData()
        mime.setImageData(qimg)
        mime.setData("image/png", QByteArray(data))
        if bmp_bytes:
            mime.setData("image/bmp", QByteArray(bmp_bytes))

        clipboard = QApplication.clipboard()
        clipboard.setMimeData(mime)

    def save_image(self, parent):
        img = self.export_image()
        path, _ = QFileDialog.getSaveFileName(
            parent, "Сохранить изображение", "",
            "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)")
        if not path:
            return None
        if path.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        img.save(path)
        return Path(path).name

    def toggle_live_text(self):
        return self.live_manager.toggle()

    def collage_available(self):
        return any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(HISTORY_DIR.glob("*.jpeg"))
