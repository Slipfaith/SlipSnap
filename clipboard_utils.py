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
}

WINDOWS_DIB_ALIASES = {
    "CF_DIB": (
        'application/x-qt-windows-mime;value="CF_DIB"',
    ),
    "CF_DIBV5": (
        'application/x-qt-windows-mime;value="CF_DIBV5"',
    ),
}


def _argb_dib_v5_bytes(img: Image.Image) -> bytes:
    """Return CF_DIBV5 bytes for an RGBA image preserving the alpha channel."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    width, height = img.size
    if not width or not height:
        return b""

    stride = ((width * 32 + 31) // 32) * 4
    size_image = stride * height

    # clang-format off
    header_bytes = struct.pack(
        "<IiiHHIIiiII"  # BITMAPINFOHEADER fields
        "IIII"  # channel masks for BI_BITFIELDS
        "I"  # color space type
        "9I"  # CIEXYZTRIPLE endpoints (unused)
        "7I",  # gamma/intent/profile fields
        124,  # bV5Size
        width,  # bV5Width
        -height,  # bV5Height (negative -> top-down DIB)
        1,  # bV5Planes
        32,  # bV5BitCount
        3,  # bV5Compression = BI_BITFIELDS
        size_image,  # bV5SizeImage
        2835,  # bV5XPelsPerMeter (~72 DPI)
        2835,  # bV5YPelsPerMeter
        0,  # bV5ClrUsed
        0,  # bV5ClrImportant
        0x00FF0000,  # bV5RedMask
        0x0000FF00,  # bV5GreenMask
        0x000000FF,  # bV5BlueMask
        0xFF000000,  # bV5AlphaMask
        0x73524742,  # bV5CSType = LCS_sRGB
        *(0 for _ in range(9)),  # bV5Endpoints (unused)
        0,  # bV5GammaRed
        0,  # bV5GammaGreen
        0,  # bV5GammaBlue
        0x00000002,  # bV5Intent = LCS_GM_GRAPHICS
        0,  # bV5ProfileData
        0,  # bV5ProfileSize
        0,  # bV5Reserved
    )
    # clang-format on

    if len(header_bytes) != 124:
        return b""

    pixel_bytes = img.tobytes("raw", "BGRA")

    return header_bytes + pixel_bytes


def _bgr_dib_bytes(img: Image.Image) -> bytes:
    """Return CF_DIB bytes without alpha for compatibility consumers."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    width, height = img.size
    if not width or not height:
        return b""

    stride = ((width * 24 + 31) // 32) * 4
    size_image = stride * height

    header_bytes = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize = BITMAPINFOHEADER
        width,  # biWidth
        height,  # biHeight (positive -> bottom-up DIB)
        1,  # biPlanes
        24,  # biBitCount
        0,  # biCompression = BI_RGB
        size_image,  # biSizeImage
        2835,  # biXPelsPerMeter (~72 DPI)
        2835,  # biYPelsPerMeter
        0,  # biClrUsed
        0,  # biClrImportant
    )

    # CF_DIB expects pixel data in BGR byte order. Word/Outlook reject
    # buffers that are supplied as RGB, so convert explicitly.
    bgr_bytes = img.convert("RGB").tobytes("raw", "BGR")
    row_bytes = width * 3
    padding = stride - row_bytes
    pad = b"\x00" * padding

    rows = []
    for row in range(height - 1, -1, -1):
        start = row * row_bytes
        end = start + row_bytes
        rows.append(bgr_bytes[start:end])
        if padding:
            rows.append(pad)

    pixel_bytes = b"".join(rows)

    if len(pixel_bytes) != size_image:
        return b""

    return header_bytes + pixel_bytes


def pil_to_qimage_with_png(img: Image.Image) -> Tuple[QImage, bytes, bytes, bytes]:
    """Return image encodings suitable for populating the clipboard."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    qimg = QImage.fromData(png_data, "PNG")
    if qimg.format() != QImage.Format_ARGB32:
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

    dib_v5_bytes = _argb_dib_v5_bytes(img)
    dib_bytes = _bgr_dib_bytes(img)

    return qimg, png_data, dib_v5_bytes, dib_bytes


def set_clipboard_from_qimage(
    qimg: QImage, png_data: bytes, dib_v5_bytes: bytes, dib_bytes: bytes
) -> None:
    """Populate the clipboard with standard image formats for broad compatibility."""

    mime = QMimeData()
    mime.setImageData(qimg)

    png_qbytes = QByteArray(png_data)
    mime.setData("image/png", png_qbytes)

    if sys.platform.startswith("win"):
        for alias in WINDOWS_IMAGE_MIME_ALIASES.get("image/png", ()):  # pragma: no cover - platform specific
            mime.setData(alias, png_qbytes)

        if dib_v5_bytes:
            dib_v5_qbytes = QByteArray(dib_v5_bytes)
            for alias in WINDOWS_DIB_ALIASES.get("CF_DIBV5", ()):  # pragma: no cover - platform specific
                mime.setData(alias, dib_v5_qbytes)

        if dib_bytes:
            dib_qbytes = QByteArray(dib_bytes)
            for alias in WINDOWS_DIB_ALIASES.get("CF_DIB", ()):  # pragma: no cover - platform specific
                mime.setData(alias, dib_qbytes)

    QGuiApplication.clipboard().setMimeData(mime)


def copy_pil_image_to_clipboard(img: Image.Image) -> QImage:
    """Copy a PIL image to the clipboard preserving transparency."""

    qimg, png_data, dib_v5_bytes, dib_bytes = pil_to_qimage_with_png(img)
    set_clipboard_from_qimage(qimg, png_data, dib_v5_bytes, dib_bytes)
    return qimg
