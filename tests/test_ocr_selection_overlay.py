# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import QApplication
from unittest.mock import patch

from design_tokens import Palette, Typography
from editor.ocr_overlay import OcrCapture
from editor.ui.canvas import Canvas
from logic import qimage_to_pil
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

    def _apply_lines(self, lines: list[tuple[str, tuple[int, int, int, int]]], *, flush: bool = True):
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
        if flush:
            overlay._flush_geometry_update()
        return overlay

    def test_long_text_selection_stays_inside_ocr_block_with_readable_glyphs(self) -> None:
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
        self.assertTrue(visual.text_item.isVisible())
        self.assertEqual(visual.text_item.font().family(), Typography.UI_FAMILY)
        self.assertEqual(visual.text_item.brush().color(), QColor(Palette.OCR_TEXT_SELECTED_FOREGROUND))
        self.assertEqual(visual.selection.brush().color().alpha(), 255)
        self.assertLessEqual(
            visual.selection.path().boundingRect().right(),
            block.width() + 0.01,
        )

    def _apply_raster(self, background: str, foreground: str, provider: str = "mistral"):
        image = QImage(400, 120, QImage.Format_RGB32)
        image.fill(QColor(background))
        painter = QPainter(image)
        font = QFont(Typography.UI_FAMILY)
        font.setPixelSize(16)
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        texts = ["First target last", "Вторая строка"]
        baselines = [30, 94]
        ink_rects = []
        for text, baseline in zip(texts, baselines):
            painter.drawText(QPointF(24, baseline), text)
            ink_rects.append(QFontMetricsF(font).tightBoundingRect(text).translated(24, baseline))
        painter.end()
        self.canvas.close()
        self.canvas = Canvas(image)
        capture = OcrCapture(
            image=qimage_to_pil(image),
            scene_rect=QRectF(0, 0, 400, 120),
            pixel_size=(400, 120),
            anchor_item=self.canvas.pixmap_item,
        )
        result = OcrResult(
            text="\n".join(texts),
            language_tag="eng",
            words=[OcrWord(text=text, bbox=(10, 10 + index * 50, 370, 50), line_id=(0, 0, index))
                   for index, text in enumerate(texts)],
            provider=provider,
        )

        overlay = self.canvas.ocr_overlay
        overlay.apply_result(result, capture)
        overlay.set_active(True)
        overlay._flush_geometry_update()
        return overlay, image, ink_rects

    def _render_scene(self) -> QImage:
        image = QImage(400, 120, QImage.Format_RGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        self.canvas.scene.render(painter, QRectF(0, 0, 400, 120), QRectF(0, 0, 400, 120))
        painter.end()
        return image

    def test_selection_is_opaque_readable_and_leaves_unselected_pixels_unchanged(self) -> None:
        for provider in ("mistral", "gemini"):
            for background, foreground in (("#171717", "white"), ("white", "#171717")):
                with self.subTest(provider=provider, background=background):
                    overlay, original, _ = self._apply_raster(background, foreground, provider)
                    self.assertEqual(self._render_scene(), original)
                    overlay.select_word_at(overlay._char_scene_rects[0][8].center())
                    self.assertEqual(overlay.selected_text(), "target")
                    rendered = self._render_scene()
                    visual = overlay._line_visuals[0]
                    selected_rect = visual.selection.sceneBoundingRect().toAlignedRect()
                    pixels = [rendered.pixelColor(x, y)
                              for x in range(selected_rect.left(), selected_rect.right())
                              for y in range(selected_rect.top(), selected_rect.bottom())]
                    self.assertIn(QColor(*Palette.OCR_TEXT_SELECTION), pixels)
                    self.assertIn(QColor(Palette.OCR_TEXT_SELECTED_FOREGROUND), pixels)
                    for y in range(original.height()):
                        for x in range(original.width()):
                            if not selected_rect.contains(x, y):
                                self.assertEqual(rendered.pixel(x, y), original.pixel(x, y))
                    overlay.clear_selection()
                    self.assertEqual(self._render_scene(), original)

    def test_coarse_boxes_follow_actual_ink_and_preserve_empty_line_spacing(self) -> None:
        overlay, _, expected_ink = self._apply_raster("#171717", "white")
        overlay.select_all()
        for actual, expected in zip(overlay._scene_line_rects, expected_ink):
            for a, b in ((actual.left(), expected.left()), (actual.top(), expected.top()),
                         (actual.width(), expected.width()), (actual.height(), expected.height())):
                self.assertAlmostEqual(a, b, delta=2)
        self.assertEqual(self._render_scene().pixelColor(100, 60), QColor("#171717"))

    def test_selection_follows_anchor_scale_and_move_without_relayout_on_zoom(self) -> None:
        overlay, _, _ = self._apply_raster("white", "black")
        overlay.select_all()
        selected_text = overlay.selected_text()
        original = QRectF(overlay._scene_line_rects[0])
        self.canvas.pixmap_item.setScale(1.75)
        self.canvas.pixmap_item.setPos(14, 21)
        overlay._flush_geometry_update()
        mapped = overlay._scene_line_rects[0]
        self.assertAlmostEqual(mapped.left(), original.left() * 1.75 + 14)
        self.assertAlmostEqual(mapped.top(), original.top() * 1.75 + 21)
        self.assertAlmostEqual(mapped.width(), original.width() * 1.75)
        self.assertEqual(overlay.selected_text(), selected_text)
        with patch.object(overlay, "_update_word_visual_geometry") as rebuild:
            self.canvas.scale(2, 2)
            overlay._flush_geometry_update()
            rebuild.assert_not_called()

    def test_export_and_repeated_ocr_capture_exclude_selection_but_restore_it(self) -> None:
        overlay, original, _ = self._apply_raster("white", "black")
        baseline_canvas = Canvas(original)
        baseline = baseline_canvas.export_image()
        baseline_canvas.close()
        overlay.select_all()
        before = self._render_scene()
        self.assertEqual(self.canvas.export_image(), baseline)
        self.assertEqual(self.canvas.current_ocr_capture().image, baseline)
        self.assertEqual(self._render_scene(), before)
        self.assertTrue(overlay.has_selection())

    def test_select_all_before_delayed_geometry_update_selects_every_character(self) -> None:
        overlay = self._apply_lines([("Small text", (20, 20, 80, 9))], flush=False)
        overlay.select_all()
        self.assertEqual(overlay.selected_text(), "Small text")

    def test_rtl_drag_selects_logical_text_and_paints_its_visual_cells(self) -> None:
        overlay = self._apply_lines([("שלום עולם", (20, 20, 180, 20))])
        positions = overlay._caret_scene_positions[0]
        self.assertGreater(positions[0], positions[4])
        overlay.start_selection(QPointF(positions[0], 30))
        overlay.finish_selection(QPointF(positions[4], 30))
        self.assertEqual(overlay.selected_text(), "שלום")
        selection = overlay._line_visuals[0].selection.sceneBoundingRect()
        for rect in overlay._char_scene_rects[0][:4]:
            self.assertTrue(selection.contains(rect.center()))

    def test_non_bmp_character_does_not_offset_following_word_selection(self) -> None:
        overlay = self._apply_lines([("One 😀 target", (20, 20, 220, 20))])
        overlay.select_word_at(overlay._char_scene_rects[0][-2].center())
        self.assertEqual(overlay.selected_text(), "target")


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
