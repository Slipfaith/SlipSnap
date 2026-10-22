# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from video_capture import _logical_to_physical_rect, hud_position


class _FakeScreen:
    def __init__(self, rect: QRect, dpr: float):
        self._rect = rect
        self._dpr = dpr

    def geometry(self) -> QRect:
        return QRect(self._rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)

    def devicePixelRatio(self) -> float:
        return self._dpr


def _region(left: int, top: int, width: int, height: int) -> dict:
    return {"left": left, "top": top, "width": width, "height": height}


class HudPositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # Laptop 1920x1080 @125% + external 1920x1080 @100% to the right.
        self.laptop = _FakeScreen(QRect(0, 0, 1536, 864), 1.25)
        self.external = _FakeScreen(QRect(1920, 0, 1920, 1080), 1.0)
        self.screens = [self.laptop, self.external]

    def _hud_phys(self, pos: QPoint, screen) -> QRect:
        return _logical_to_physical_rect(screen, QRect(pos.x(), pos.y(), 360, 134))

    def test_default_top_centre_when_region_is_elsewhere(self) -> None:
        pos = hud_position(360, 134, _region(0, 700, 400, 300), self.screens)
        default = hud_position(360, 134, None, self.screens)
        self.assertEqual(pos, default)

    def test_moves_away_from_region_covering_top_centre(self) -> None:
        region = _region(500, 0, 1000, 500)
        pos = hud_position(360, 134, region, self.screens)
        hud = self._hud_phys(pos, self.laptop)
        self.assertFalse(hud.intersects(QRect(500, 0, 1000, 500)))
        self.assertTrue(QRect(0, 0, 1536, 864).contains(QRect(pos, hud.size() / 1.25)))

    def test_whole_laptop_recorded_puts_hud_on_other_screen(self) -> None:
        pos = hud_position(360, 134, _region(0, 0, 1920, 1080), self.screens)
        self.assertGreaterEqual(pos.x(), 1920)
        self.assertFalse(self._hud_phys(pos, self.external).intersects(QRect(0, 0, 1920, 1080)))


if __name__ == "__main__":
    unittest.main()
