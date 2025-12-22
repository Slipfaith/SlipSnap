from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import QGraphicsPixmapItem


class HighQualityPixmapItem(QGraphicsPixmapItem):
    """Pixmap item that keeps the original image for crisp scaling."""

    def __init__(self, image: QImage):
        self._base_image: QImage = QImage(image)
        self._natural_size: QSize = image.size()
        self._current_scale: float = 1.0
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
        self._current_scale = 1.0
        self._update_display_for_scale(1.0)

    # ---- scaling ---------------------------------------------------------
    def setScale(self, scale: float) -> None:  # type: ignore[override]
        if scale <= 0:
            scale = 0.01
        if self._base_image.isNull():
            self._current_scale = scale
            QGraphicsPixmapItem.setScale(self, scale)
            return
        if math.isclose(scale, self._current_scale, rel_tol=1e-4):
            return
        self._current_scale = scale
        self._update_display_for_scale(scale)

    def paint(self, painter, option, widget=None):  # type: ignore[override]
        """Render pixmap without the default dashed selection frame."""
        if self.pixmap().isNull():
            return
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.restore()

    def scale(self) -> float:  # type: ignore[override]
        return self._current_scale

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

        current_scale = self._current_scale or 1.0
        self._update_display_for_scale(current_scale)

    def reset_scale_tracking(self) -> None:
        """Force the item to treat current pixmap as the base image."""
        pix = self.pixmap()
        if pix.isNull():
            return
        self._base_image = pix.toImage()
        self._natural_size = self._base_image.size()
        self._current_scale = 1.0
        self._update_display_for_scale(1.0)

    def _update_display_for_scale(self, scale: float) -> None:
        if self._base_image.isNull():
            QGraphicsPixmapItem.setScale(self, scale)
            return

        if math.isclose(scale, 1.0, rel_tol=1e-4):
            self._set_pixmap_no_sync(QPixmap.fromImage(self._base_image))
            QGraphicsPixmapItem.setScale(self, 1.0)
            return

        if scale < 1.0:
            pixmap = QPixmap.fromImage(self._base_image)
            pixmap.setDevicePixelRatio(1.0 / scale)
            self._set_pixmap_no_sync(pixmap)
            QGraphicsPixmapItem.setScale(self, 1.0)
            return

        target_w = max(1, int(round(self._natural_size.width() * scale)))
        target_h = max(1, int(round(self._natural_size.height() * scale)))
        scaled_image = self._base_image.scaled(
            target_w,
            target_h,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        self._set_pixmap_no_sync(QPixmap.fromImage(scaled_image))
        QGraphicsPixmapItem.setScale(self, 1.0)
