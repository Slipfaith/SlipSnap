# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QToolButton

from editor.ui.toolbar_factory import create_tools_toolbar


class _CanvasStub:
    def __init__(self) -> None:
        self.pen_mode = "pencil"
        self.tool_calls: list[str] = []

    def set_tool(self, tool: str) -> None:
        self.tool_calls.append(tool)

    def set_pen_mode(self, mode: str) -> None:
        self.pen_mode = mode


class EraserToolbarButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = QMainWindow()
        self.canvas = _CanvasStub()
        create_tools_toolbar(self.window, self.canvas)
        self.canvas.tool_calls.clear()
        self.button = self.window.findChild(QToolButton, "eraserToolButton")
        self.menu = self.window.findChild(QMenu, "eraserModeMenu")

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self._app.processEvents()

    def test_eraser_has_no_menu_arrow_and_uses_right_click_menu(self) -> None:
        self.assertIsNotNone(self.button)
        self.assertIsNotNone(self.menu)
        self.assertIsNone(self.button.menu())
        self.assertEqual(self.button.contextMenuPolicy(), Qt.CustomContextMenu)

        menu_opened: list[bool] = []
        self.menu.aboutToShow.connect(lambda: menu_opened.append(True))
        QTimer.singleShot(0, self.menu.close)
        self.button.customContextMenuRequested.emit(QPoint(2, 2))

        self.assertEqual(menu_opened, [True])

    def test_left_click_reuses_mode_selected_from_context_menu(self) -> None:
        screenshot_action = self.window.findChild(
            QAction,
            "eraseScreenshotAction",
        )
        self.assertIsNotNone(screenshot_action)

        screenshot_action.trigger()
        self.assertEqual(self.canvas.tool_calls, ["erase_screenshot"])

        self.canvas.tool_calls.clear()
        self.button.click()
        self.assertEqual(self.canvas.tool_calls, ["erase_screenshot"])


if __name__ == "__main__":
    unittest.main()
