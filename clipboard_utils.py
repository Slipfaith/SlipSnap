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

    stride = width * 4
    size_image = stride * height

    header = BytesIO()
    # BITMAPV5HEADER structure (124 bytes) with sRGB color space and alpha mask.
    header.write(
        struct.pack(
            "<IiiHHIIiiII",  # BITMAPV5HEADER basic fields
            124,  # bV5Size
            width,  # bV5Width
            -height,  # bV5Height (negative for top-down DIB)
            1,  # bV5Planes
            32,  # bV5BitCount
            3,  # bV5Compression = BI_BITFIELDS
            size_image,  # bV5SizeImage
            2835,  # bV5XPelsPerMeter (~72 DPI)
            2835,  # bV5YPelsPerMeter
            0,  # bV5ClrUsed
            0,  # bV5ClrImportant
        )
    )
    header.write(struct.pack("<IIII", 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000))
    header.write(struct.pack("<I", 0x73524742))  # bV5CSType = 'sRGB'
    header.write(struct.pack("<9I", *([0] * 9)))  # bV5Endpoints
    header.write(struct.pack("<III", 0, 0, 0))  # bV5GammaRed/Green/Blue
    header.write(struct.pack("<I", 4))  # bV5Intent = LCS_GM_GRAPHICS
    header.write(struct.pack("<III", 0, 0, 0))  # bV5ProfileData/ProfileSize/Reserved

    header_bytes = header.getvalue()
    if len(header_bytes) != 124:
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

    payloads = []

    png_bytes = QByteArray(png_data)
    payloads.append(("image/png", png_bytes))

    if dib_bytes:
        payloads.append(("image/bmp", QByteArray(dib_bytes)))

    for mime_name, data in payloads:
        mime.setData(mime_name, data)
        if sys.platform.startswith("win"):
            for alias in WINDOWS_IMAGE_MIME_ALIASES.get(mime_name, ()):  # pragma: no cover - platform specific
                mime.setData(alias, data)

    QGuiApplication.clipboard().setMimeData(mime)


def copy_pil_image_to_clipboard(img: Image.Image) -> QImage:
    """Copy a PIL image to the clipboard preserving transparency."""

    qimg, png_data, dib_bytes = pil_to_qimage_with_png(img)
    set_clipboard_from_qimage(qimg, png_data, dib_bytes)
    return qimg
