# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QToolButton

from editor.editor_window import EditorWindow
from editor.ui.ocr_cloud_dialog import OcrCloudSettingsDialog


class OcrSettingsAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        image = QImage(64, 64, QImage.Format_RGB32)
        image.fill(0xFFFFFFFF)
        self.window = EditorWindow(image, {})

    def tearDown(self) -> None:
        self.window.close()
        self._app.processEvents()

    def test_ocr_toolbar_button_has_no_arrow_and_uses_right_click_menu(self) -> None:
        button = self.window._ocr_button

        self.assertIsNotNone(button)
        self.assertIsNone(button.menu())
        self.assertEqual(button.popupMode(), QToolButton.DelayedPopup)
        self.assertEqual(button.contextMenuPolicy(), Qt.CustomContextMenu)

        menu_opened: list[bool] = []
        self.window._ocr_menu.aboutToShow.connect(lambda: menu_opened.append(True))
        QTimer.singleShot(0, self.window._ocr_menu.close)
        QTest.mouseClick(button, Qt.RightButton)

        self.assertEqual(menu_opened, [True])

    def test_settings_button_opens_dialog_after_popup_closes(self) -> None:
        settings_action = next(
            action
            for action in self.window._ocr_menu.actions()
            if action.text() == "Настроить API-ключи…"
        )
        open_settings = Mock(return_value=False)
        self.window._open_ocr_cloud_settings = open_settings

        settings_action.trigger()
        self._app.processEvents()

        open_settings.assert_called_once_with()

    def test_left_click_triggers_ocr_action(self) -> None:
        action = self.window._ocr_button.defaultAction()
        action.triggered.disconnect()
        triggered = Mock()
        action.triggered.connect(triggered)

        QTest.mouseClick(self.window._ocr_button, Qt.LeftButton)

        triggered.assert_called_once_with()

    def test_settings_open_failure_is_visible_instead_of_silent(self) -> None:
        with (
            patch(
                "editor.editor_window.OcrCloudSettingsDialog",
                side_effect=RuntimeError("packaged dialog failure"),
            ),
            patch.object(QMessageBox, "critical") as critical,
        ):
            opened = self.window._open_ocr_cloud_settings()

        self.assertFalse(opened)
        critical.assert_called_once()
        self.assertIn("packaged dialog failure", critical.call_args.args[2])

    def test_key_dialog_contains_editors_for_both_providers(self) -> None:
        dialog = OcrCloudSettingsDialog(self.window)

        self.assertIsNotNone(dialog.findChild(QLineEdit, "mistralApiKeyEdit"))
        self.assertIsNotNone(dialog.findChild(QLineEdit, "geminiApiKeyEdit"))

        dialog.close()


if __name__ == "__main__":
    unittest.main()
