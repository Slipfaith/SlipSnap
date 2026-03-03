# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from video_capture import VideoSaveOptionsDialog


class VideoSaveOptionsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_gif_checkbox_toggles_by_format(self) -> None:
        dlg = VideoSaveOptionsDialog(None, Path("tests"), "clip", "gif")
        self.assertTrue(dlg._add_memes_checkbox.isEnabled())
        self.assertTrue(dlg._add_memes_checkbox.isChecked())

        dlg._add_memes_checkbox.setChecked(False)
        dlg._format_combo.setCurrentIndex(0)  # MP4
        self.assertFalse(dlg._add_memes_checkbox.isEnabled())
        self.assertFalse(dlg._add_memes_checkbox.isChecked())

        dlg._format_combo.setCurrentIndex(1)  # GIF
        self.assertTrue(dlg._add_memes_checkbox.isEnabled())
        self.assertFalse(dlg._add_memes_checkbox.isChecked())
        dlg.close()

    def test_accept_gif_selection_with_extension(self) -> None:
        dlg = VideoSaveOptionsDialog(None, Path("tests"), "clip", "gif")
        dlg._path_edit.setText("tests/fixtures/new_clip")
        dlg._format_combo.setCurrentIndex(1)  # GIF
        dlg._add_memes_checkbox.setChecked(True)
        dlg.accept()

        path, output_format, add_to_memes = dlg.selection()
        self.assertEqual(output_format, "gif")
        self.assertEqual(path.suffix.lower(), ".gif")
        self.assertTrue(add_to_memes)
        dlg.close()

    def test_accept_mp4_disables_add_to_memes(self) -> None:
        dlg = VideoSaveOptionsDialog(None, Path("tests"), "clip", "mp4")
        dlg._path_edit.setText("tests/fixtures/new_clip")
        dlg._format_combo.setCurrentIndex(0)  # MP4
        dlg.accept()

        path, output_format, add_to_memes = dlg.selection()
        self.assertEqual(output_format, "mp4")
        self.assertEqual(path.suffix.lower(), ".mp4")
        self.assertFalse(add_to_memes)
        dlg.close()


if __name__ == "__main__":
    unittest.main()