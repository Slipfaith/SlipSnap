# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from PySide6.QtWidgets import QApplication

from packaged_selftest import run_ocr_self_test


class _DialogStub:
    def __init__(self, _parent) -> None:
        self.visible = False

    def findChild(self, _widget_type, _name):
        return object()

    def show(self) -> None:
        self.visible = True

    def isVisible(self) -> bool:
        return self.visible

    def close(self) -> None:
        self.visible = False

    def deleteLater(self) -> None:
        return None


class PackagedOcrSelfTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QApplication.instance() or QApplication([])

    def test_exercises_dialog_credentials_and_both_providers(self) -> None:
        app = Mock()
        app.windowIcon.return_value.isNull.return_value = False
        window = Mock()
        with (
            patch("packaged_selftest.EditorWindow", return_value=window),
            patch("packaged_selftest.OcrCloudSettingsDialog", _DialogStub),
            patch("packaged_selftest.get_api_key", side_effect=["m-key", "g-key"]),
            patch("packaged_selftest.check_cloud_provider") as check_provider,
        ):
            run_ocr_self_test(app)

        self.assertEqual(
            check_provider.call_args_list,
            [call("mistral", "m-key"), call("gemini", "g-key")],
        )
        self.assertGreaterEqual(app.processEvents.call_count, 3)
        window.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
