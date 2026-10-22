# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from editor.tools.scissors_tool import ScissorsTool
from editor.ui.canvas import Canvas
from editor.ui.high_quality_pixmap_item import HighQualityPixmapItem


class _DummyOverlay:
    def __init__(self, *_args, **_kwargs):
        pass

    def clear(self):
        return None

    def set_active(self, _active):
        return None


class ScissorsToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        image = QImage(200, 100, QImage.Format_RGB32)
        image.fill(QColor("blue"))
        self.canvas = Canvas(image)
        self.canvas.set_tool("scissors")
        self.tool: ScissorsTool = self.canvas.active_tool

    def tearDown(self) -> None:
        self.canvas.close()
        self._overlay_patch.stop()
        self._app.processEvents()

    def _cut(self, *points) -> None:
        self.tool.press(QPointF(*points[0]))
        for pt in points[1:-1]:
            self.tool.move(QPointF(*pt))
        self.tool.release(QPointF(*points[-1]))

    def _alpha(self, item, x: int, y: int) -> int:
        return item.pixmap().toImage().pixelColor(x, y).alpha()

    def test_cut_across_screenshot_splits_it_into_two_pieces(self) -> None:
        item = self.canvas.pixmap_item
        self._cut((100, -10), (100, 50), (100, 110))

        pieces = self.tool.piece_map(item)
        left = pieces.label_at(20, 50)
        right = pieces.label_at(180, 50)
        self.assertIsNotNone(left)
        self.assertNotEqual(left, right)
        self.assertTrue(pieces.is_separate(left))

    def test_stroke_stopping_near_edge_still_separates(self) -> None:
        item = self.canvas.pixmap_item
        # Starts and ends ~10px inside the image.
        self._cut((100, 10), (100, 50), (100, 90))

        pieces = self.tool.piece_map(item)
        self.assertNotEqual(pieces.label_at(20, 50), pieces.label_at(180, 50))

    def test_partial_cut_does_not_separate(self) -> None:
        item = self.canvas.pixmap_item
        self._cut((100, 40), (100, 50), (100, 60))

        pieces = self.tool.piece_map(item)
        label = pieces.label_at(20, 50)
        self.assertEqual(label, pieces.label_at(180, 50))
        self.assertFalse(pieces.is_separate(label))
        self.assertFalse(self.tool.delete_piece_at(item, QPointF(20, 50)))

    def test_delete_piece_leaves_transparency_and_paper_edge_with_undo(self) -> None:
        item = self.canvas.pixmap_item
        self._cut((100, -10), (100, 50), (100, 110))

        self.assertTrue(self.tool.delete_piece_at(item, QPointF(20, 50)))

        self.assertEqual(self._alpha(item, 20, 50), 0)
        self.assertEqual(self._alpha(item, 180, 50), 255)
        self.assertEqual(item.pixmap().toImage().pixelColor(180, 50), QColor("blue"))
        # The kept side gets a light paper rim right next to the tear.
        rim = [item.pixmap().toImage().pixelColor(x, 50) for x in range(96, 112)]
        self.assertTrue(any(c.alpha() == 255 and c.red() > 200 for c in rim))

        self.canvas.undo()
        self.assertEqual(self._alpha(item, 20, 50), 255)
        self.canvas.redo()
        self.assertEqual(self._alpha(item, 20, 50), 0)

    def test_deleting_from_menu_switches_back_to_selection(self) -> None:
        item = self.canvas.pixmap_item
        self._cut((100, -10), (100, 50), (100, 110))

        with patch.object(ScissorsTool, "_exec_menu", staticmethod(lambda menu, _pos: menu.actions()[0])):
            self.tool.show_context_menu(QPointF(20, 50), QPoint(0, 0))

        self.assertEqual(self._alpha(item, 20, 50), 0)
        self.assertEqual(self.canvas._tool, "select")

    def test_one_cut_splits_several_screenshots(self) -> None:
        other_img = QImage(200, 100, QImage.Format_RGB32)
        other_img.fill(QColor("red"))
        other = HighQualityPixmapItem(other_img)
        other.setData(0, "screenshot")
        other.setPos(0, 150)
        self.canvas.scene.addItem(other)

        self._cut((100, -10), (100, 120), (100, 260))

        for item in (self.canvas.pixmap_item, other):
            pieces = self.tool.piece_map(item)
            self.assertNotEqual(pieces.label_at(20, 50), pieces.label_at(180, 50))

        self.canvas.undo()
        self.assertEqual(self.tool.cuts_for(other), [])
        self.assertEqual(self.tool.cuts_for(self.canvas.pixmap_item), [])

    def test_cut_lines_are_not_exported(self) -> None:
        self._cut((100, -10), (100, 50), (100, 110))
        exported = self.canvas.export_image().convert("RGBA")
        self.assertEqual(exported.getpixel((100, 50)), (0, 0, 255, 255))


if __name__ == "__main__":
    unittest.main()
