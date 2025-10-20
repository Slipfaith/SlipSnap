from __future__ import annotations

from io import BytesIO
import struct
import sys
from typing import Tuple

from PIL import Image
from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication, QImage


WINDOWS_IMAGE_MIME_ALIASES = {
    "image/png": (
        "PNG",
        'application/x-qt-windows-mime;value="PNG"',
    ),
    "image/bmp": (
        'application/x-qt-windows-mime;value="CF_DIB"',
        'application/x-qt-windows-mime;value="CF_DIBV5"',
    ),
}


def _argb_dib_bytes(img: Image.Image) -> bytes:
    """Return CF_DIB bytes for an RGBA image preserving the alpha channel."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    width, height = img.size
    if not width or not height:
        return b""

    # Align the stride to a 4 byte boundary (requirement for DIBs).
    stride = ((width * 32 + 31) // 32) * 4
    size_image = stride * height

    header = BytesIO()
    # BITMAPINFOHEADER (40 bytes) followed by explicit channel masks for BI_BITFIELDS.
    header.write(
        struct.pack(
            "<IiiHHIIiiII",
            40,  # biSize
            width,  # biWidth
            -height,  # biHeight (negative -> top-down DIB)
            1,  # biPlanes
            32,  # biBitCount
            3,  # biCompression = BI_BITFIELDS
            size_image,  # biSizeImage
            2835,  # biXPelsPerMeter (~72 DPI)
            2835,  # biYPelsPerMeter
            0,  # biClrUsed
            0,  # biClrImportant
        )
    )
    # RGB and alpha masks to keep the channel order explicit.
    header.write(struct.pack("<IIII", 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000))

    header_bytes = header.getvalue()
    if len(header_bytes) != 56:
        return b""

    pixel_bytes = img.tobytes("raw", "BGRA")

    return header_bytes + pixel_bytes


def pil_to_qimage_with_png(img: Image.Image) -> Tuple[QImage, bytes, bytes]:
    """Return a QImage, PNG bytes and CF_DIB compatible bytes for a PIL image."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    qimg = QImage.fromData(png_data, "PNG")
    if qimg.format() != QImage.Format_ARGB32:
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

    dib_bytes = _argb_dib_bytes(img)

    return qimg, png_data, dib_bytes


def set_clipboard_from_qimage(qimg: QImage, png_data: bytes, dib_bytes: bytes) -> None:
    """Populate the clipboard with standard image formats for broad compatibility."""

    mime = QMimeData()
    mime.setImageData(qimg)

    png_qbytes = QByteArray(png_data)
    mime.setData("image/png", png_qbytes)

    if sys.platform.startswith("win"):
        for alias in WINDOWS_IMAGE_MIME_ALIASES.get("image/png", ()):  # pragma: no cover - platform specific
            mime.setData(alias, png_qbytes)

        if dib_bytes:
            dib_qbytes = QByteArray(dib_bytes)
            for alias in WINDOWS_IMAGE_MIME_ALIASES.get("image/bmp", ()):  # pragma: no cover - platform specific
                mime.setData(alias, dib_qbytes)

    QGuiApplication.clipboard().setMimeData(mime)


def copy_pil_image_to_clipboard(img: Image.Image) -> QImage:
    """Copy a PIL image to the clipboard preserving transparency."""

    qimg, png_data, dib_bytes = pil_to_qimage_with_png(img)
    set_clipboard_from_qimage(qimg, png_data, dib_bytes)
    return qimg
