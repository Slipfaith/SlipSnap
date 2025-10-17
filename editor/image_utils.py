from __future__ import annotations

from typing import List

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QPixmap


def _convert_to_qimage(data) -> QImage | None:
    """Try to convert clipboard/drag payload to QImage."""
    if isinstance(data, QImage):
        return data
    if isinstance(data, QPixmap):
        return data.toImage()
    # Some platforms return QVariant wrappers that have toImage
    convert = getattr(data, "toImage", None)
    if callable(convert):
        return convert()
    return None


def images_from_mime(mime: QMimeData | None) -> List[QImage]:
    """Extract QImages contained in mime data."""
    images: List[QImage] = []
    if mime is None:
        return images

    if mime.hasImage():
        qimg = _convert_to_qimage(mime.imageData())
        if qimg is not None and not qimg.isNull():
            images.append(qimg)

    if mime.hasUrls():
        for url in mime.urls():
            if isinstance(url, QUrl) and url.isLocalFile():
                local_path = url.toLocalFile()
                qimg = QImage(local_path)
                if not qimg.isNull():
                    images.append(qimg)

    return images
