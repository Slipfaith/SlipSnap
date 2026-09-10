# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from editor.ui.canvas import Canvas


class _DummyOverlay:
    def __init__(self, *_args, **_kwargs):
        pass

    def clear(self):
        return None

    def set_active(self, _active):
        return None


class EraserToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        image = QImage(120, 90, QImage.Format_RGB32)
        image.fill(QColor("white"))
        self.canvas = Canvas(image)

    def tearDown(self) -> None:
        self.canvas.close()
        self._overlay_patch.stop()
        self._app.processEvents()

    def _base_alpha(self, x: int, y: int) -> int:
        return self.canvas.pixmap_item.pixmap().toImage().pixelColor(x, y).alpha()

    def test_screenshot_eraser_creates_transparency_with_undo_redo(self) -> None:
        self.canvas.set_tool("erase_screenshot")
        tool = self.canvas.active_tool
        tool.set_size(24)

        tool.press(QPointF(50, 40))
        tool.release(QPointF(50, 40))

        self.assertEqual(self._base_alpha(50, 40), 0)
        self.assertEqual(self.canvas.undo_stack.count(), 1)

        self.canvas.undo()
        self.assertEqual(self._base_alpha(50, 40), 255)

        self.canvas.redo()
        self.assertEqual(self._base_alpha(50, 40), 0)

    def test_element_eraser_does_not_modify_screenshot(self) -> None:
        self.canvas.set_tool("erase")
        tool = self.canvas.active_tool

        tool.press(QPointF(50, 40))
        tool.release(QPointF(50, 40))

        self.assertEqual(self._base_alpha(50, 40), 255)
        self.assertEqual(self.canvas.undo_stack.count(), 0)

    def test_screenshot_eraser_leaves_annotation_layer_intact(self) -> None:
        annotation_image = QImage(30, 30, QImage.Format_ARGB32)
        annotation_image.fill(QColor("red"))
        annotation = QGraphicsPixmapItem(QPixmap.fromImage(annotation_image))
        annotation.setData(0, "annotation")
        annotation.setPos(35, 25)
        annotation.setZValue(10)
        self.canvas.scene.addItem(annotation)

        self.canvas.set_tool("erase_screenshot")
        tool = self.canvas.active_tool
        tool.press(QPointF(50, 40))
        tool.release(QPointF(50, 40))

        self.assertEqual(annotation.pixmap().toImage().pixelColor(15, 15).alpha(), 255)
        self.assertEqual(self._base_alpha(50, 40), 0)

    def test_element_eraser_still_erases_annotation_with_undo(self) -> None:
        annotation_image = QImage(30, 30, QImage.Format_RGB32)
        annotation_image.fill(QColor("red"))
        annotation = QGraphicsPixmapItem(QPixmap.fromImage(annotation_image))
        annotation.setData(0, "annotation")
        annotation.setPos(35, 25)
        annotation.setZValue(10)
        self.canvas.scene.addItem(annotation)

        self.canvas.set_tool("erase")
        tool = self.canvas.active_tool
        tool.press(QPointF(50, 40))
        tool.release(QPointF(50, 40))

        self.assertEqual(annotation.pixmap().toImage().pixelColor(15, 15).alpha(), 0)
        self.assertEqual(self._base_alpha(50, 40), 255)

        self.canvas.undo()
        self.assertEqual(annotation.pixmap().toImage().pixelColor(15, 15).alpha(), 255)

if __name__ == "__main__":
    unittest.main()
