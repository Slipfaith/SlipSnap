from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLineF
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsLineItem

from editor.ui.canvas import (
    ANIMATION_DRAW,
    ANIMATION_PULSE,
    ANIMATION_DRAW_ACTIVE_MS,
    ANIMATION_DRAW_HOLD_MS,
    ITEM_ANIMATION_ROLE,
    Canvas,
)


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


class CanvasItemAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._tmp_dir = Path(__file__).resolve().parent / ".tmp"
        cls._tmp_dir.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self._overlay_patch = patch("editor.ui.canvas.OcrSelectionOverlay", new=_DummyOverlay)
        self._overlay_patch.start()
        from PySide6.QtGui import QImage

        base = QImage(280, 180, QImage.Format_ARGB32)
        base.fill(0xFFFFFFFF)
        self._canvas = Canvas(base)
        self._canvas.resize(420, 280)
        self._canvas.show()
        self._app.processEvents()

    def tearDown(self) -> None:
        self._canvas.close()
        self._overlay_patch.stop()
        self._app.processEvents()

    def _add_line(self) -> QGraphicsLineItem:
        item = QGraphicsLineItem(QLineF(40, 60, 230, 120))
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        item.setData(0, "line")
        self._canvas.scene.addItem(item)
        return item

    def test_has_gif_content_true_when_item_has_animation(self) -> None:
        item = self._add_line()
        self.assertFalse(self._canvas.has_gif_content())
        item.setData(ITEM_ANIMATION_ROLE, ANIMATION_PULSE)
        self.assertTrue(self._canvas.has_gif_content())
        self.assertEqual(self._canvas._effective_drag_extension(), ".gif")

    def test_save_animated_gif_with_item_draw_animation(self) -> None:
        item = self._add_line()
        item.setData(ITEM_ANIMATION_ROLE, ANIMATION_DRAW)
        target = self._tmp_dir / "item_draw.gif"
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        saved = self._canvas.save_animated_gif(target, selected_only=False)
        self.assertTrue(saved)
        self.assertTrue(target.is_file())
        with PILImage.open(target) as gif:
            self.assertGreater(getattr(gif, "n_frames", 1), 1)
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass

    def test_live_draw_animation_updates_and_restores_line(self) -> None:
        item = self._add_line()
        item.setData(ITEM_ANIMATION_ROLE, ANIMATION_DRAW)
        base_line = QLineF(item.line())

        self._canvas._refresh_live_item_animation_state()
        self.assertTrue(self._canvas._item_animation_timer.isActive())
        self._canvas._on_item_animation_tick()

        animated_line = QLineF(item.line())
        changed = (
            abs(animated_line.p2().x() - base_line.p2().x()) > 1e-3
            or abs(animated_line.p2().y() - base_line.p2().y()) > 1e-3
        )
        self.assertTrue(changed)

        self._canvas._stop_live_item_animation()
        restored = QLineF(item.line())
        self.assertAlmostEqual(restored.p1().x(), base_line.p1().x(), places=3)
        self.assertAlmostEqual(restored.p1().y(), base_line.p1().y(), places=3)
        self.assertAlmostEqual(restored.p2().x(), base_line.p2().x(), places=3)
        self.assertAlmostEqual(restored.p2().y(), base_line.p2().y(), places=3)

    def test_draw_animation_holds_at_end_then_restarts(self) -> None:
        item = self._add_line()
        item.setData(ITEM_ANIMATION_ROLE, ANIMATION_DRAW)
        states = self._canvas._relevant_item_animations()
        self.assertTrue(states)
        base_line = QLineF(item.line())

        # During hold window line must remain fully drawn.
        self._canvas._apply_item_animations_at(states, ANIMATION_DRAW_ACTIVE_MS + 200)
        held_line = QLineF(item.line())
        self.assertAlmostEqual(held_line.p2().x(), base_line.p2().x(), places=3)
        self.assertAlmostEqual(held_line.p2().y(), base_line.p2().y(), places=3)

        # After full cycle the animation restarts from the beginning.
        self._canvas._apply_item_animations_at(states, ANIMATION_DRAW_ACTIVE_MS + ANIMATION_DRAW_HOLD_MS + 10)
        restarted_line = QLineF(item.line())
        self.assertLess(QLineF(restarted_line.p1(), restarted_line.p2()).length(), base_line.length() * 0.25)

    def test_large_item_with_pulse_is_ignored(self) -> None:
        large = QGraphicsLineItem(QLineF(10, 20, 360, 20))
        large.setFlag(QGraphicsItem.ItemIsSelectable, True)
        large.setFlag(QGraphicsItem.ItemIsMovable, True)
        large.setData(0, "line")
        large.setData(ITEM_ANIMATION_ROLE, ANIMATION_PULSE)
        self._canvas.scene.addItem(large)

        self.assertFalse(self._canvas._is_pulse_eligible(large))
        self.assertFalse(self._canvas.has_gif_content())


if __name__ == "__main__":
    unittest.main()
