# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QKeySequenceEdit

from gui import Launcher


class HotkeySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.cfg = {
            "capture_hotkey": "Ctrl+Alt+S",
            "video_hotkey": "Ctrl+Alt+V",
            "video_duration_sec": 6,
            "video_fps": 15,
            "shape": "rect",
        }
        self.launcher = Launcher(self.cfg)

    def tearDown(self) -> None:
        self.launcher.force_close()
        self._app.processEvents()

    def test_accepting_unchanged_settings_does_not_reregister_hotkeys(self) -> None:
        capture_events: list[str] = []
        video_events: list[str] = []
        self.launcher.hotkey_changed.connect(capture_events.append)
        self.launcher.video_hotkey_changed.connect(video_events.append)

        with patch.object(QDialog, "exec", return_value=QDialog.Accepted), patch(
            "gui.save_config"
        ) as save_config_mock:
            self.launcher._on_hotkey()

        self.assertEqual(capture_events, [])
        self.assertEqual(video_events, [])
        save_config_mock.assert_not_called()

    def test_only_changed_hotkey_is_emitted(self) -> None:
        capture_events: list[str] = []
        video_events: list[str] = []
        self.launcher.hotkey_changed.connect(capture_events.append)
        self.launcher.video_hotkey_changed.connect(video_events.append)

        def accept_with_new_capture(dialog: QDialog) -> int:
            edits = dialog.findChildren(QKeySequenceEdit)
            self.assertEqual(len(edits), 2)
            edits[0].setKeySequence(QKeySequence("Ctrl+Shift+S"))
            return QDialog.Accepted

        with patch.object(QDialog, "exec", new=accept_with_new_capture), patch(
            "gui.save_config"
        ) as save_config_mock:
            self.launcher._on_hotkey()

        self.assertEqual(capture_events, ["Ctrl+Shift+S"])
        self.assertEqual(video_events, [])
        self.assertEqual(self.cfg["capture_hotkey"], "Ctrl+Shift+S")
        save_config_mock.assert_called_once_with(self.cfg)


if __name__ == "__main__":
    unittest.main()
