# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import QApplication

from editor.ocr_overlay import OcrCapture
from editor.ui.canvas import Canvas
from ocr_models import OcrResult, OcrWord


class OcrSelectionOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        image = QImage(400, 120, QImage.Format_RGB32)
        image.fill(0xFFFFFFFF)
        self.canvas = Canvas(image)

    def tearDown(self) -> None:
        self.canvas.close()
        self._app.processEvents()

    def _apply_lines(self, lines: list[tuple[str, tuple[int, int, int, int]]]):
        capture = OcrCapture(
            image=Image.new("RGB", (400, 120), "white"),
            scene_rect=QRectF(0, 0, 400, 120),
            pixel_size=(400, 120),
            anchor_item=self.canvas.pixmap_item,
        )
        result = OcrResult(
            text="\n".join(text for text, _bbox in lines),
            language_tag="eng",
            words=[
                OcrWord(text=text, bbox=bbox, line_id=(0, line_idx, 0))
                for line_idx, (text, bbox) in enumerate(lines)
            ],
            provider="mistral",
        )
        overlay = self.canvas.ocr_overlay
        overlay.apply_result(result, capture)
        overlay.set_active(True)
        overlay._flush_geometry_update()
        return overlay

    def test_long_text_selection_stays_inside_ocr_block_without_text_overlay(self) -> None:
        text = "MISTRALAPI=abcdefghijklmnopqrstuvwxyz0123456789"
        block = QRectF(30, 40, 180, 18)
        overlay = self._apply_lines([(text, (30, 40, 180, 18))])
        overlay.select_all()

        chars = overlay._char_scene_rects[0]
        self.assertEqual(len(chars), len(text))
        self.assertGreaterEqual(chars[0].left(), block.left())
        self.assertLessEqual(chars[-1].right(), block.right() + 0.01)
        for previous, current in zip(chars, chars[1:]):
            self.assertGreaterEqual(current.left(), previous.right() - 0.01)

        visual = overlay._line_visuals[0]
        self.assertFalse(visual.text_item.isVisible())
        self.assertEqual(visual.selection.brush().color().alpha(), 255)
        self.assertFalse(visual.selection.dark_background)
        self.assertLessEqual(
            visual.selection.path().boundingRect().right(),
            block.width() + 0.01,
        )

    def test_dark_screenshot_uses_contrast_preserving_selection(self) -> None:
        capture = OcrCapture(
            image=Image.new("RGB", (400, 120), "#171717"),
            scene_rect=QRectF(0, 0, 400, 120),
            pixel_size=(400, 120),
            anchor_item=self.canvas.pixmap_item,
        )
        result = OcrResult(
            text="exact glyphs",
            language_tag="eng",
            words=[OcrWord(text="exact glyphs", bbox=(20, 20, 180, 20), line_id=(0, 0, 0))],
            provider="gemini",
        )

        overlay = self.canvas.ocr_overlay
        overlay.apply_result(result, capture)
        overlay.set_active(True)
        overlay._flush_geometry_update()

        self.assertTrue(overlay._line_visuals[0].selection.dark_background)

    def test_click_places_caret_without_selecting_character(self) -> None:
        overlay = self._apply_lines([("Hello world", (20, 20, 180, 20))])
        point = overlay._char_scene_rects[0][4].center()

        overlay.start_selection(point)
        overlay.finish_selection(point)

        self.assertFalse(overlay.has_selection())
        self.assertEqual(overlay.selected_text(), "")

    def test_drag_selects_exact_characters_in_both_directions(self) -> None:
        overlay = self._apply_lines([("Hello world", (20, 20, 180, 20))])
        selection_events: list[str] = []
        overlay.selectionChanged.connect(selection_events.append)
        chars = overlay._char_scene_rects[0]
        start = QPointF(chars[0].left(), chars[0].center().y())
        end = QPointF(chars[4].right(), chars[4].center().y())

        overlay.start_selection(start)
        overlay.update_drag(end)
        self.assertEqual(overlay.selected_text(), "Hello")
        self.assertEqual(selection_events[-1], "Hello")

        overlay.start_selection(end)
        overlay.update_drag(start)
        self.assertEqual(overlay.selected_text(), "Hello")

    def test_drag_across_lines_preserves_word_processor_reading_order(self) -> None:
        overlay = self._apply_lines(
            [
                ("Hello world", (20, 20, 180, 20)),
                ("Second line", (20, 55, 180, 20)),
            ]
        )
        first_line = overlay._char_scene_rects[0]
        second_line = overlay._char_scene_rects[1]
        start = QPointF(first_line[6].left(), first_line[6].center().y())
        end = QPointF(second_line[2].right(), second_line[2].center().y())

        overlay.start_selection(start)
        overlay.update_drag(end)

        self.assertEqual(overlay.selected_text(), "world\nSec")

    def test_double_click_selects_one_word(self) -> None:
        overlay = self._apply_lines([("Hello world!", (20, 20, 180, 20))])

        overlay.select_word_at(overlay._char_scene_rects[0][8].center())

        self.assertEqual(overlay.selected_text(), "world")

    def test_shift_click_extends_existing_selection(self) -> None:
        overlay = self._apply_lines([("Hello world", (20, 20, 180, 20))])
        chars = overlay._char_scene_rects[0]
        start = QPointF(chars[0].left(), chars[0].center().y())
        after_hello = QPointF(chars[4].right(), chars[4].center().y())
        after_world = QPointF(chars[-1].right(), chars[-1].center().y())
        overlay.start_selection(start)
        overlay.finish_selection(after_hello)

        overlay.start_selection(after_world, extend=True)

        self.assertEqual(overlay.selected_text(), "Hello world")

    def test_ctrl_a_selects_ocr_text_without_switching_tools(self) -> None:
        overlay = self._apply_lines(
            [
                ("First line", (20, 20, 180, 20)),
                ("Second line", (20, 55, 180, 20)),
            ]
        )
        self.canvas.set_tool("ocr")
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier)

        self.canvas.keyPressEvent(event)

        self.assertTrue(event.isAccepted())
        self.assertEqual(self.canvas._tool, "ocr")
        self.assertEqual(overlay.selected_text(), "First line\nSecond line")

    def test_ctrl_c_copies_only_selected_text_and_escape_clears_it(self) -> None:
        overlay = self._apply_lines([("Hello world", (20, 20, 180, 20))])
        overlay.select_word_at(overlay._char_scene_rects[0][8].center())
        self.canvas.set_tool("ocr")
        QApplication.clipboard().clear()

        copy_event = QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
        self.canvas.keyPressEvent(copy_event)

        self.assertTrue(copy_event.isAccepted())
        self.assertEqual(QApplication.clipboard().text(), "world")

        escape_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        self.canvas.keyPressEvent(escape_event)
        self.assertTrue(escape_event.isAccepted())
        self.assertFalse(overlay.has_selection())


if __name__ == "__main__":
    unittest.main()
