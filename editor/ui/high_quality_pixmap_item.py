# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import QGraphicsPixmapItem


class HighQualityPixmapItem(QGraphicsPixmapItem):
    """Pixmap item that keeps the original image for crisp scaling."""

    def __init__(self, image: QImage):
        self._base_image: QImage = QImage(image)
        self._natural_size: QSize = image.size()
        self._suppress_updates: bool = False
        super().__init__(QPixmap.fromImage(self._base_image))
        self.setTransformationMode(Qt.SmoothTransformation)

    # ---- helpers ---------------------------------------------------------
    def _set_pixmap_no_sync(self, pixmap: QPixmap) -> None:
        self._suppress_updates = True
        try:
            QGraphicsPixmapItem.setPixmap(self, pixmap)
        finally:
            self._suppress_updates = False

    def original_image(self) -> QImage:
        return QImage(self._base_image)

    def set_original_image(self, image: QImage) -> None:
        self._base_image = QImage(image)
        self._natural_size = image.size()
        self._set_pixmap_no_sync(QPixmap.fromImage(self._base_image))
        QGraphicsPixmapItem.setScale(self, 1.0)

    # ---- scaling ---------------------------------------------------------
    def setScale(self, scale: float) -> None:  # type: ignore[override]
        if scale <= 0:
            scale = 0.01
        # Keep the source raster unchanged while the item is resized. Qt's
        # smooth scene transform avoids allocating a new, potentially huge,
        # pixmap for every mouse-move event.
        QGraphicsPixmapItem.setScale(self, scale)

    def paint(self, painter, option, widget=None):  # type: ignore[override]
        """Render pixmap without the default dashed selection frame."""
        if self.pixmap().isNull():
            return
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.restore()

    # ---- pixmap synchronization -----------------------------------------
    def setPixmap(self, pixmap: QPixmap) -> None:  # type: ignore[override]
        if self._suppress_updates:
            QGraphicsPixmapItem.setPixmap(self, pixmap)
            return

        if self._natural_size.isEmpty():
            self._natural_size = pixmap.size()

        base_image = pixmap.toImage()
        self._base_image = base_image
        if not base_image.size().isEmpty():
            self._natural_size = base_image.size()
        self._set_pixmap_no_sync(QPixmap.fromImage(self._base_image))

    def reset_scale_tracking(self) -> None:
        """Force the item to treat current pixmap as the base image."""
        pix = self.pixmap()
        if pix.isNull():
            return
        self._base_image = pix.toImage()
        self._natural_size = self._base_image.size()
        QGraphicsPixmapItem.setScale(self, 1.0)
