# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from gui import SelectionOverlayBase
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


if __name__ == "__main__":
    unittest.main()
