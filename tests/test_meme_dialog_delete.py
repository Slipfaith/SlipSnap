# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from editor.ui.meme_library_dialog import MemesDialog


_FIXTURE_GIF = Path(__file__).resolve().parent / "fixtures" / "sample.gif"


class MemeDialogDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_remove_selected_releases_gif_movie_and_calls_delete(self) -> None:
        with (
            patch("editor.ui.meme_library_dialog.list_memes", return_value=[_FIXTURE_GIF]),
            patch("editor.ui.meme_library_dialog.QMessageBox.question", return_value=QMessageBox.Yes),
            patch("editor.ui.meme_library_dialog.delete_memes") as delete_mock,
            patch("pathlib.Path.exists", return_value=False),
        ):
            dlg = MemesDialog()
            dlg.refresh()
            dlg._load_thumb_batch()

            self.assertIn(_FIXTURE_GIF, dlg._gif_movies)
            item = dlg._list.item(0)
            item.setSelected(True)

            dlg._remove_selected()

            delete_mock.assert_called()
            self.assertNotIn(_FIXTURE_GIF, dlg._gif_movies)
            dlg.close()

    def test_rename_base_sanitization(self) -> None:
        self.assertEqual(MemesDialog._sanitize_rename_base("good_name"), "good_name")
        self.assertEqual(MemesDialog._sanitize_rename_base("bad<>:\"/\\|?*name"), "badname")
        self.assertEqual(MemesDialog._sanitize_rename_base("..."), "")
        self.assertEqual(MemesDialog._sanitize_rename_base("CON"), "")

    def test_window_size_restored_and_persisted(self) -> None:
        cfg = {"meme_dialog_width": 640, "meme_dialog_height": 700}
        with patch("editor.ui.meme_library_dialog.save_config") as save_cfg_mock:
            dlg = MemesDialog(cfg=cfg)
            self.assertGreaterEqual(dlg.width(), 640)
            self.assertGreaterEqual(dlg.height(), 700)
            dlg.resize(660, 710)
            dlg._persist_window_size()
            self.assertEqual(cfg["meme_dialog_width"], 660)
            self.assertEqual(cfg["meme_dialog_height"], 710)
            self.assertTrue(save_cfg_mock.called)
            dlg.close()


if __name__ == "__main__":
    unittest.main()