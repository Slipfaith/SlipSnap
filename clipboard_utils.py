from __future__ import annotations

import struct
from io import BytesIO
import sys
from typing import Tuple

from PIL import Image
from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication, QImage


def qimage_to_dib_bytes(qimg: QImage) -> bytes:
    """Convert a QImage to a top-down DIB byte stream preserving alpha."""

    if qimg.isNull():
        raise ValueError("QImage is null")

    if qimg.format() != QImage.Format_ARGB32:
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

    header = b"".join(
        (
            struct.pack(
                "<IiiHHIIiiII",
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
            ),
            struct.pack(
                "<IIII",
                0x00FF0000,  # red mask
                0x0000FF00,  # green mask
                0x000000FF,  # blue mask
                0xFF000000,  # alpha mask
            ),
            struct.pack("<I", 0x57696E20),  # LCS_WINDOWS_COLOR_SPACE
            struct.pack("<9i", *([0] * 9)),  # CIEXYZ endpoints
            struct.pack(
                "<IIIIIII",
                0,  # gamma red
                0,  # gamma green
                0,  # gamma blue
                4,  # LCS_GM_IMAGES
                0,  # profile data
                0,  # profile size
                0,  # reserved
            ),
        )
    )

    return header + buffer


def pil_to_qimage_with_png(img: Image.Image) -> Tuple[QImage, bytes]:
    """Return a QImage and PNG byte representation for a PIL image."""

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    qimg = QImage.fromData(png_data, "PNG")
    if qimg.format() != QImage.Format_ARGB32:
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

    return qimg, png_data


def set_clipboard_from_qimage(qimg: QImage, png_data: bytes) -> None:
    """Populate the clipboard with QImage, PNG and DIB representations."""

    bmp_bytes = qimage_to_dib_bytes(qimg)

    mime = QMimeData()
    png_bytes = QByteArray(png_data)
    mime.setImageData(qimg)
    mime.setData("image/png", png_bytes)
    if sys.platform.startswith("win"):
        mime.setData("PNG", png_bytes)
        mime.setData(
            "application/x-qt-windows-mime;value=\"PNG\"",
            png_bytes,
        )
    if bmp_bytes:
        bmp_qbytes = QByteArray(bmp_bytes)
        mime.setData("image/bmp", bmp_qbytes)
        if sys.platform.startswith("win"):
            mime.setData(
                "application/x-qt-windows-mime;value=\"CF_DIB\"",
                bmp_qbytes,
            )
            mime.setData(
                "application/x-qt-windows-mime;value=\"CF_DIBV5\"",
                bmp_qbytes,
            )

    QGuiApplication.clipboard().setMimeData(mime)


def copy_pil_image_to_clipboard(img: Image.Image) -> QImage:
    """Copy a PIL image to the clipboard preserving transparency."""

    qimg, png_data = pil_to_qimage_with_png(img)
    set_clipboard_from_qimage(qimg, png_data)
    return qimg
