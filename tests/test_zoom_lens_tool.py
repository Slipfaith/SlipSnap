from __future__ import annotations

import os
import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QKeyEvent, QMovie, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsPixmapItem

from editor.ui.canvas import Canvas
from editor.ui.zoom_lens_item import ZoomLensItem


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


class _AnimatedGifTestItem(QGraphicsPixmapItem):
    def __init__(self, gif_path: Path):
        super().__init__()
        self._gif_path = Path(gif_path)
        self._movie = QMovie(str(self._gif_path))
        if not self._movie.isValid():
            raise ValueError(f"GIF is invalid: {gif_path}")
        self._movie.frameChanged.connect(self._on_frame_changed)
        self._movie.start()
        self._on_frame_changed(0)

    def _on_frame_changed(self, _frame_no: int) -> None:
        pix = self._movie.currentPixmap()
        if not pix.isNull():
            self.setPixmap(pix)

    def source_path(self) -> Path:
        return self._gif_path


class ZoomLensToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        img = QImage(220, 160, QImage.Format_ARGB32)
        img.fill(0xFFFFFFFF)
        self._canvas = Canvas(img)
        self._canvas.resize(360, 260)
        self._canvas.show()
        self._app.processEvents()

    def tearDown(self) -> None:
        self._canvas.close()
        self._overlay_patch.stop()
        self._app.processEvents()

    def test_zoom_lens_settings_clamped(self) -> None:
        self._canvas.set_zoom_lens_radius(10)
        self.assertEqual(self._canvas.zoom_lens_radius(), 60)
        self._canvas.set_zoom_lens_radius(500)
        self.assertEqual(self._canvas.zoom_lens_radius(), 260)

        self._canvas.set_zoom_lens_factor(0.5)
        self.assertAlmostEqual(self._canvas.zoom_lens_factor(), 1.2, places=2)
        self._canvas.set_zoom_lens_factor(12.0)
        self.assertAlmostEqual(self._canvas.zoom_lens_factor(), 8.0, places=2)

    def test_zoom_lens_items_can_be_added_and_persist_across_tools(self) -> None:
        self._canvas.set_tool("zoom_lens")
        first = self._canvas.add_zoom_lens_item(QPointF(70, 60), radius_px=90, zoom_factor=2.0)
        second = self._canvas.add_zoom_lens_item(QPointF(150, 90), radius_px=120, zoom_factor=3.5)

        self._canvas.set_tool("select")

        lenses = [item for item in self._canvas.scene.items() if isinstance(item, ZoomLensItem)]
        self.assertEqual(len(lenses), 2)
        self.assertIn(first, lenses)
        self.assertIn(second, lenses)
        self.assertEqual(first.radius_px(), 90)
        self.assertEqual(second.radius_px(), 120)
        self.assertAlmostEqual(second.zoom_factor(), 3.5, places=1)

    def test_draw_foreground_renders_zoom_lens_overlay(self) -> None:
        self._canvas.add_zoom_lens_item(QPointF(100, 80), radius_px=80, zoom_factor=2.5)

        target = QImage(360, 260, QImage.Format_ARGB32)
        target.fill(0x00000000)
        painter = QPainter(target)
        self._canvas.drawForeground(painter, QRectF())
        painter.end()

        self.assertNotEqual(target.pixelColor(100, 80).alpha(), 0)

    def test_zoom_lens_escape_clears_live_preview(self) -> None:
        self._canvas.set_tool("zoom_lens")
        self._canvas._zoom_lens_cursor_vp = QPoint(120, 70)
        ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        self._canvas.keyPressEvent(ev)
        self.assertIsNone(self._canvas._zoom_lens_cursor_vp)

    def test_export_image_contains_zoom_lens_visuals(self) -> None:
        self._canvas.add_zoom_lens_item(QPointF(110, 70), radius_px=50, zoom_factor=3.0)
        out = self._canvas.export_image().convert("RGB")
        extrema = out.getextrema()
        mins = [pair[0] for pair in extrema]
        self.assertTrue(any(v < 250 for v in mins))

    def test_save_animated_gif_keeps_animation_with_zoom_lens(self) -> None:
        root_tmp = Path.cwd() / ".codex_tmp"
        root_tmp.mkdir(parents=True, exist_ok=True)
        tmp_dir = root_tmp / f"slipsnap_zoom_lens_test_{os.getpid()}_{int(time.time() * 1000)}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            src_gif = tmp_dir / "src.gif"
            frame_a = Image.new("RGBA", (48, 36), (255, 0, 0, 255))
            frame_b = Image.new("RGBA", (48, 36), (0, 0, 255, 255))
            frame_a.save(
                src_gif,
                format="GIF",
                save_all=True,
                append_images=[frame_b],
                duration=[120, 120],
                loop=0,
            )

            gif_item = _AnimatedGifTestItem(src_gif)
            gif_item.setFlag(QGraphicsItem.ItemIsMovable, True)
            gif_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            gif_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
            gif_item.setData(0, "gif")
            gif_item.setData(1, "gif")
            gif_item.setData(2, str(src_gif))
            gif_item.setPos(60, 40)
            self._canvas.scene.addItem(gif_item)
            self._canvas.add_zoom_lens_item(QPointF(84, 58), radius_px=36, zoom_factor=2.0)

            target = tmp_dir / "out.gif"
            self.assertTrue(self._canvas.save_animated_gif(target, selected_only=False))
            self.assertTrue(target.exists())

            with Image.open(target) as exported:
                frame_count = int(getattr(exported, "n_frames", 1))
                self.assertGreaterEqual(frame_count, 2)
                exported.seek(0)
                first_frame = exported.convert("RGB").copy()
                exported.seek(1)
                second_frame = exported.convert("RGB").copy()
                self.assertNotEqual(first_frame.tobytes(), second_frame.tobytes())
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
