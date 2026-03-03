# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QImage, QMovie
from PySide6.QtWidgets import QApplication

from clipboard_utils import SLIPSNAP_MEME_MIME
from editor.editor_window import EditorWindow


_FIXTURE_GIF = Path(__file__).resolve().parent / "fixtures" / "sample.gif"


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


class EditorGifInsertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._tmp_dir = Path(__file__).resolve().parent / ".tmp"
        cls._tmp_dir.mkdir(parents=True, exist_ok=True)
        cls._animated_fixture = cls._tmp_dir / "animated_sample.gif"
        frame1 = PILImage.new("RGBA", (24, 24), (255, 0, 0, 255))
        frame2 = PILImage.new("RGBA", (24, 24), (0, 0, 255, 255))
        frame1.save(
            cls._animated_fixture,
            format="GIF",
            save_all=True,
            append_images=[frame2],
            duration=[80, 120],
            loop=0,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls._animated_fixture.unlink(missing_ok=True)
        except Exception:
            pass
        drag_dir = cls._tmp_dir / "drag_export"
        try:
            (drag_dir / "snap_01.gif").unlink(missing_ok=True)
        except Exception:
            pass
        try:
            drag_dir.rmdir()
        except Exception:
            pass

    def setUp(self) -> None:
        base = QImage(96, 72, QImage.Format_ARGB32)
        base.fill(0xFFFFFFFF)
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        self._ocr_patch = patch.object(EditorWindow, "_setup_ocr_button", autospec=True, return_value=None)
        self._ocr_patch.start()
        self._win = EditorWindow(base, {})
        self._win.hide()

    def tearDown(self) -> None:
        self._win.close()
        self._ocr_patch.stop()
        self._overlay_patch.stop()
        self._app.processEvents()

    def _gif_items(self):
        return [item for item in self._win.canvas.scene.items() if item.data(1) == "gif"]

    def test_insert_gif_item_from_path(self) -> None:
        inserted = self._win._insert_gif_item(_FIXTURE_GIF, item_tag="test_gif")
        self.assertTrue(inserted)
        items = self._gif_items()
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0].data(0), "test_gif")
        movie = getattr(items[0], "_movie", None)
        self.assertIsNotNone(movie)
        self.assertTrue(movie.isValid())
        self.assertNotEqual(movie.state(), QMovie.NotRunning)

    def test_paste_gif_from_custom_mime(self) -> None:
        mime = QMimeData()
        payload = {"kind": "gif", "path": str(_FIXTURE_GIF)}
        mime.setData(SLIPSNAP_MEME_MIME, json.dumps(payload).encode("utf-8"))

        inserted = self._win._paste_gif_from_mime(mime)
        self.assertTrue(inserted)
        self.assertGreaterEqual(len(self._gif_items()), 1)

    def test_export_image_with_gif_item(self) -> None:
        inserted = self._win._insert_gif_item(_FIXTURE_GIF, item_tag="test_gif")
        self.assertTrue(inserted)

        exported = self._win.logic.export_image()
        self.assertTrue(hasattr(exported, "size"))
        self.assertGreater(exported.size[0], 0)
        self.assertGreater(exported.size[1], 0)

    def test_canvas_drag_extension_switches_to_gif_when_gif_present(self) -> None:
        self.assertEqual(self._win.canvas._effective_drag_extension(), ".png")
        inserted = self._win._insert_gif_item(_FIXTURE_GIF, item_tag="test_gif")
        self.assertTrue(inserted)
        self.assertEqual(self._win.canvas._effective_drag_extension(), ".gif")

    def test_save_animated_gif_exports_multiple_frames(self) -> None:
        inserted = self._win._insert_gif_item(self._animated_fixture, item_tag="test_gif")
        self.assertTrue(inserted)
        target = self._tmp_dir / "scene.gif"
        target.unlink(missing_ok=True)
        saved = self._win.canvas.save_animated_gif(target)
        self.assertTrue(saved)
        self.assertTrue(target.is_file())
        with PILImage.open(target) as gif:
            self.assertGreater(getattr(gif, "n_frames", 1), 1)
        target.unlink(missing_ok=True)

    def test_external_drag_writes_animated_gif_file(self) -> None:
        inserted = self._win._insert_gif_item(self._animated_fixture, item_tag="test_gif")
        self.assertTrue(inserted)
        drag_dir = self._tmp_dir / "drag_export"
        drag_dir.mkdir(parents=True, exist_ok=True)
        target = drag_dir / "snap_01.gif"
        target.unlink(missing_ok=True)
        with (
            patch("editor.ui.canvas.tempfile.mkdtemp", return_value=str(drag_dir)),
            patch("editor.ui.canvas.QDrag.exec", return_value=Qt.CopyAction),
        ):
            self._win.canvas._start_external_drag()
        self.assertTrue(target.is_file())
        with PILImage.open(target) as gif:
            self.assertGreater(getattr(gif, "n_frames", 1), 1)
        target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()