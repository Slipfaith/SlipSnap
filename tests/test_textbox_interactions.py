# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from editor.text_tools import EditableTextItem, TextManager
from editor.ui.canvas import Canvas


class _DummyOverlay:
    def __init__(self, *_args, **_kwargs):
        pass

    def clear(self):
        return None

    def set_active(self, _active):
        return None

    def has_selection(self):
        return False

    def has_words(self):
        return False

    def apply_result(self, *_args, **_kwargs):
        return None


class TextboxInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        image = QImage(260, 180, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        self.canvas = Canvas(image)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.canvas.resize(420, 300)
        self.canvas.show()
        self._app.processEvents()

    def tearDown(self) -> None:
        self.canvas.close()
        self._overlay_patch.stop()
        self._app.processEvents()

    def _create_placeholder_text_item(self) -> EditableTextItem:
        self.canvas.set_tool("text")
        create_pos = self.canvas.mapFromScene(QPointF(120, 90))
        outside_pos = self.canvas.mapFromScene(QPointF(25, 25))
        QTest.mouseClick(self.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, create_pos)
        self._app.processEvents()
        item = self.text_manager._current_text_item
        self.assertIsNotNone(item)
        QTest.mouseClick(self.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, outside_pos)
        self._app.processEvents()
        self.assertEqual(self.canvas._tool, "select")
        self.assertEqual(item.toPlainText(), "Введите текст...")
        return item

    def test_double_click_placeholder_enters_edit_and_replaces_all_text(self) -> None:
        item = self._create_placeholder_text_item()
        self.canvas.set_tool("select")
        click_pos = self.canvas.mapFromScene(item.sceneBoundingRect().center())

        QTest.mouseDClick(self.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, click_pos)
        self._app.processEvents()

        self.assertTrue(item._is_editing)
        self.assertTrue(item.textCursor().hasSelection())
        self.assertEqual(item.textCursor().selectedText(), "Введите текст...")

        QTest.keyClicks(self.canvas.viewport(), "Hello")
        self._app.processEvents()
        self.assertEqual(item.toPlainText(), "Hello")

    def test_click_outside_finishes_text_editing_in_select_tool(self) -> None:
        item = self._create_placeholder_text_item()
        self.canvas.set_tool("select")
        click_pos = self.canvas.mapFromScene(item.sceneBoundingRect().center())
        outside_pos = self.canvas.mapFromScene(QPointF(25, 25))

        QTest.mouseDClick(self.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, click_pos)
        self._app.processEvents()
        self.assertTrue(item._is_editing)

        QTest.mouseClick(self.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, outside_pos)
        self._app.processEvents()

        self.assertEqual(self.canvas._tool, "select")
        self.assertFalse(item._is_editing)
        self.assertEqual(item.textInteractionFlags(), Qt.NoTextInteraction)


if __name__ == "__main__":
    unittest.main()
