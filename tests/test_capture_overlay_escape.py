# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from gui import SelectionOverlayBase


class _OverlayForTest(SelectionOverlayBase):
    def _map_rect_to_image_coords(self, gr: QRect):
        return gr.x(), gr.y(), gr.width(), gr.height()


class CaptureOverlayEscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_escape_cancels_overlay_once(self) -> None:
        img = Image.new("RGB", (120, 80), "white")
        overlay = _OverlayForTest(img, {"shape": "rect", "blur_radius": 2}, QRect(0, 0, 120, 80))
        try:
            events: list[bool] = []
            overlay.cancel_all.connect(lambda: events.append(True))

            ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
            overlay.keyPressEvent(ev)
            self.assertEqual(len(events), 1)

            # Repeated cancellation should be ignored.
            overlay._cancel_selection()
            self.assertEqual(len(events), 1)
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
