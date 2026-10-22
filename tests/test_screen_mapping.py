# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtWidgets import QApplication

from gui import OverlayManager, SelectionOverlayBase
from logic import ScreenGrabber


class _FakeScreen:
    def __init__(self, rect: QRect, dpr: float):
        self._rect = rect
        self._dpr = dpr

    def geometry(self) -> QRect:
        return QRect(self._rect)

    def devicePixelRatio(self) -> float:
        return self._dpr


def _mon(left: int, top: int, width: int, height: int) -> dict:
    return {"left": left, "top": top, "width": width, "height": height}


class ScreenMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_mixed_dpi_screens_match_by_native_rect(self) -> None:
        # Laptop 1920x1080 @125% + external 1920x1080 @100%, as Qt 6 reports them.
        laptop = _FakeScreen(QRect(0, 0, 1536, 864), 1.25)
        external = _FakeScreen(QRect(1920, 0, 1920, 1080), 1.0)
        monitors = [_mon(1920, 0, 1920, 1080), _mon(0, 0, 1920, 1080)]

        mapping = ScreenGrabber._exact_match([laptop, external], monitors)

        self.assertEqual(mapping, {0: 1, 1: 0})

    def test_virtual_overlay_only_for_unscaled_desktop(self) -> None:
        grabber = ScreenGrabber.__new__(ScreenGrabber)
        mixed = [
            (_FakeScreen(QRect(0, 0, 1536, 864), 1.25), _mon(0, 0, 1920, 1080)),
            (_FakeScreen(QRect(1920, 0, 1920, 1080), 1.0), _mon(1920, 0, 1920, 1080)),
        ]
        plain = [
            (_FakeScreen(QRect(0, 0, 1920, 1080), 1.0), _mon(0, 0, 1920, 1080)),
            (_FakeScreen(QRect(1920, 0, 2560, 1440), 1.0), _mon(1920, 0, 2560, 1440)),
        ]

        self.assertFalse(grabber.is_virtual_desktop_uniform(mixed))
        self.assertTrue(grabber.is_virtual_desktop_uniform(plain))

    def test_selection_maps_local_rect_to_physical_pixels(self) -> None:
        # Overlay is 1536x864 logical on a 125% screen holding a 1920x1080 shot.
        img = Image.new("RGB", (1920, 1080), "white")
        overlay = SelectionOverlayBase(img, {"shape": "rect"}, QRect(0, 0, 1536, 864))
        try:
            self.assertEqual(
                overlay._map_rect_to_image_coords(QRect(400, 200, 160, 80)),
                (500, 250, 200, 100),
            )
            # Rects touching the edge are clamped to the image.
            self.assertEqual(
                overlay._map_rect_to_image_coords(QRect(1456, 784, 80, 80)),
                (1820, 980, 100, 100),
            )
        finally:
            overlay.close()

    def test_selection_spanning_two_screens_is_stitched(self) -> None:
        # Laptop 1920x1080 @125% (red) left of an external 1920x1080 @100% (blue).
        left_img = Image.new("RGB", (1920, 1080), "red")
        right_img = Image.new("RGB", (1920, 1080), "blue")
        manager = OverlayManager({"shape": "rect"})
        left = SelectionOverlayBase(left_img, {"shape": "rect"}, QRect(0, 0, 1536, 864))
        right = SelectionOverlayBase(right_img, {"shape": "rect"}, QRect(1920, 0, 1920, 1080))
        left.attach_group(manager, QRect(0, 0, 1920, 1080))
        right.attach_group(manager, QRect(1920, 0, 1920, 1080))
        manager._overlays = [left, right]
        try:
            # Local point on the scaled screen maps to physical pixels.
            self.assertEqual(left._local_to_physical(QPoint(1536, 432)), QPoint(1920, 540))

            manager.begin_selection(QPoint(1800, 100))
            manager.update_selection(QPoint(2100, 300))
            # Each overlay sees the shared selection in its own local units.
            self.assertEqual(left._selection_local_rectf(), QRectF(1440, 80, 240, 160))
            self.assertEqual(right._selection_local_rectf(), QRectF(-120, 100, 300, 200))

            result = manager.compose_selection(manager._selection_rect())
            self.assertEqual(result.size, (300, 200))
            self.assertEqual(result.getpixel((60, 100)), (255, 0, 0, 255))
            self.assertEqual(result.getpixel((240, 100)), (0, 0, 255, 255))
        finally:
            manager._overlays = []
            left.close()
            right.close()

    def test_area_outside_monitors_stays_transparent(self) -> None:
        # Lower screen is narrower, so the bottom-right corner is a gap.
        manager = OverlayManager({"shape": "rect"})
        top = SelectionOverlayBase(Image.new("RGB", (200, 100), "red"), {"shape": "rect"}, QRect(0, 0, 200, 100))
        bottom = SelectionOverlayBase(Image.new("RGB", (100, 100), "blue"), {"shape": "rect"}, QRect(0, 100, 100, 100))
        top.attach_group(manager, QRect(0, 0, 200, 100))
        bottom.attach_group(manager, QRect(0, 100, 100, 100))
        manager._overlays = [top, bottom]
        try:
            result = manager.compose_selection(QRect(50, 50, 100, 100))
            self.assertEqual(result.getpixel((25, 75)), (0, 0, 255, 255))
            self.assertEqual(result.getpixel((75, 75))[3], 0)
        finally:
            manager._overlays = []
            top.close()
            bottom.close()


if __name__ == "__main__":
    unittest.main()
