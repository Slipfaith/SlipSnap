# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QToolButton

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
        button.customContextMenuRequested.emit(QPoint(2, 2))

        self.assertEqual(menu_opened, [True])

    def test_settings_button_opens_dialog_after_popup_closes(self) -> None:
        settings_button = next(
            button
            for button in self.window._ocr_menu.findChildren(QPushButton)
            if button.text() == "Настроить API-ключи…"
        )
        open_settings = Mock(return_value=False)
        self.window._open_ocr_cloud_settings = open_settings

        settings_button.click()
        self._app.processEvents()

        open_settings.assert_called_once_with()

    def test_key_dialog_contains_editors_for_both_providers(self) -> None:
        dialog = OcrCloudSettingsDialog(self.window)

        self.assertIsNotNone(dialog.findChild(QLineEdit, "mistralApiKeyEdit"))
        self.assertIsNotNone(dialog.findChild(QLineEdit, "geminiApiKeyEdit"))

        dialog.close()


if __name__ == "__main__":
    unittest.main()
