# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from editor.editor_logic import EditorLogic


class _DummyCanvas:
    def __init__(self, has_gif: bool, animated_result: bool = False):
        self._has_gif = has_gif
        self._animated_result = animated_result
        self.animated_target = None
        self.animated_selected_only = None

    def export_image(self):
        return Image.new("RGBA", (16, 10), (255, 0, 0, 255))

    def has_gif_content(self) -> bool:
        return self._has_gif

    def save_animated_gif(self, target, selected_only: bool = False) -> bool:
        self.animated_target = target
        self.animated_selected_only = selected_only
        return self._animated_result


class EditorLogicGifSaveTests(unittest.TestCase):
    def test_force_gif_save_when_canvas_has_gif(self) -> None:
        canvas = _DummyCanvas(has_gif=True)
        cfg = {"last_save_directory": str(Path.cwd())}
        logic = EditorLogic(canvas, cfg)

        with (
            patch("editor.editor_logic.QFileDialog.getSaveFileName", return_value=("snap_test", "PNG (*.png)")),
            patch("editor.editor_logic.save_config"),
            patch("PIL.Image.Image.save") as save_mock,
        ):
            filename = logic.save_image(None)

        self.assertEqual(filename, "snap_test.gif")
        args, kwargs = save_mock.call_args
        self.assertTrue(str(args[0]).lower().endswith(".gif"))
        self.assertEqual(kwargs.get("format"), "GIF")

    def test_regular_png_save_without_gif_content(self) -> None:
        canvas = _DummyCanvas(has_gif=False)
        cfg = {"last_save_directory": str(Path.cwd())}
        logic = EditorLogic(canvas, cfg)

        with (
            patch("editor.editor_logic.QFileDialog.getSaveFileName", return_value=("snap_test", "PNG (*.png)")),
            patch("editor.editor_logic.save_config"),
            patch("PIL.Image.Image.save") as save_mock,
        ):
            filename = logic.save_image(None)

        self.assertEqual(filename, "snap_test.png")
        args, kwargs = save_mock.call_args
        self.assertTrue(str(args[0]).lower().endswith(".png"))
        self.assertEqual(kwargs.get("format"), "PNG")

    def test_regular_jpeg_save_without_gif_content(self) -> None:
        canvas = _DummyCanvas(has_gif=False)
        cfg = {"last_save_directory": str(Path.cwd())}
        logic = EditorLogic(canvas, cfg)

        with (
            patch("editor.editor_logic.QFileDialog.getSaveFileName", return_value=("snap_test.jpg", "JPEG (*.jpg)")),
            patch("editor.editor_logic.save_config"),
            patch("PIL.Image.Image.save") as save_mock,
        ):
            filename = logic.save_image(None)

        self.assertEqual(filename, "snap_test.jpg")
        args, kwargs = save_mock.call_args
        self.assertTrue(str(args[0]).lower().endswith(".jpg"))
        self.assertEqual(kwargs.get("format"), "JPEG")

    def test_next_filename_extension_support(self) -> None:
        canvas = _DummyCanvas(has_gif=False)
        cfg = {"last_save_directory": str(Path.cwd())}
        logic = EditorLogic(canvas, cfg)
        self.assertTrue(logic.next_snap_filename(extension=".gif").endswith(".gif"))
        self.assertTrue(logic.next_snap_filename_for_directory(Path.cwd(), extension=".gif").endswith(".gif"))

    def test_uses_canvas_animated_export_when_available(self) -> None:
        canvas = _DummyCanvas(has_gif=True, animated_result=True)
        cfg = {"last_save_directory": str(Path.cwd())}
        logic = EditorLogic(canvas, cfg)

        with (
            patch("editor.editor_logic.QFileDialog.getSaveFileName", return_value=("snap_test", "GIF (*.gif)")),
            patch("editor.editor_logic.save_config"),
            patch("PIL.Image.Image.save") as save_mock,
        ):
            filename = logic.save_image(None)

        self.assertEqual(filename, "snap_test.gif")
        self.assertIsNotNone(canvas.animated_target)
        self.assertTrue(str(canvas.animated_target).lower().endswith(".gif"))
        self.assertFalse(canvas.animated_selected_only)
        save_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()