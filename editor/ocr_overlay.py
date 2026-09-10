# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen,
    QTextLayout, QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
)
from PIL import Image

from design_tokens import Metrics, Palette, Typography
from editor.ocr_layout import align_line_rects
from ocr_models import OcrResult, OcrWord


@dataclass
class OcrCapture:
    image: Image.Image
    scene_rect: QRectF
    pixel_size: Tuple[int, int]
    anchor_item: Optional[QGraphicsItem] = None


@dataclass
class _LineVisual:
    background: QGraphicsPathItem  # фон строки
    selection: QGraphicsPathItem   # подсветка выбранных участков
    text_item: "_SelectedTextItem"


class _SelectedTextItem(QGraphicsSimpleTextItem):
    """Draw recognized glyphs only inside the opaque selection background."""

    def __init__(self, text: str, parent: QGraphicsItem) -> None:
        super().__init__(text, parent)
        self.selection_path = QPainterPath()

    def paint(self, painter, option, widget=None) -> None:
        if self.selection_path.isEmpty():
            return
        painter.save()
        painter.setClipPath(self.mapFromParent(self.selection_path), Qt.IntersectClip)
        painter.setRenderHint(QPainter.TextAntialiasing)
        super().paint(painter, option, widget)
        painter.restore()


class OcrSelectionOverlay(QObject):
    """Overlay that maps OCR words to selectable regions on the canvas."""

    selectionChanged = Signal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.scene: QGraphicsScene = canvas.scene
        self.words: List[OcrWord] = []
        self._anchor_item: Optional[QGraphicsItem] = None
        self._anchor_local_rect: Optional[QRectF] = None
        self._capture_scene_rect: Optional[QRectF] = None
        self._active = False
        self._line_visuals: List[Optional[_LineVisual]] = []
        self._normalized_line_rects: List[Optional[QRectF]] = []
        self._scene_line_rects: List[Optional[QRectF]] = []
        self._line_texts: List[str] = []
        self._char_scene_rects: List[List[Optional[QRectF]]] = []
        self._caret_scene_positions: List[List[float]] = []
        self._selected_chars: Dict[int, Set[int]] = {}
        self._selection_anchor: Optional[Tuple[int, int]] = None
        self._selection_focus: Optional[Tuple[int, int]] = None
        self._full_text: str = ""
        self._geometry_update_in_progress = False
        self._geometry_reschedule_requested = False
        self._ignore_scene_changes = False
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(12)
        self._geometry_timer.timeout.connect(self._flush_geometry_update)

        self.canvas.viewport().installEventFilter(self)
        self.canvas.horizontalScrollBar().valueChanged.connect(self._schedule_geometry_update)
        self.canvas.verticalScrollBar().valueChanged.connect(self._schedule_geometry_update)
        self.scene.changed.connect(self._on_scene_changed)

    def clear(self) -> None:
        self.words = []
        self._anchor_item = None
        self._anchor_local_rect = None
        self._capture_scene_rect = None
        self._selection_anchor = None
        self._selection_focus = None
        self._selected_chars = {}
        self._full_text = ""
        for visual in self._line_visuals:
            if visual and visual.background.scene() is self.scene:
                self.scene.removeItem(visual.background)
        self._line_visuals = []
        self._normalized_line_rects = []
        self._scene_line_rects = []
        self._line_texts = []
        self._char_scene_rects = []
        self._caret_scene_positions = []
        self._geometry_timer.stop()
        self._geometry_reschedule_requested = False
        self.selectionChanged.emit("")

    def apply_result(self, result: OcrResult, capture: OcrCapture) -> None:
        self.clear()
        self.words = list(result.words)
        text = (result.text or "").strip()
        if not self.words and not text:
            return

        self._anchor_item = capture.anchor_item if capture.anchor_item and capture.anchor_item.scene() == self.scene else None
        self._capture_scene_rect = capture.scene_rect
        self._anchor_local_rect = None
        if self._anchor_item and self._capture_scene_rect is not None:
            self._anchor_local_rect = self._anchor_item.mapRectFromScene(self._capture_scene_rect)

        rect = self._current_scene_rect()

        if rect is None:
            return

        if not text and self.words:
            lines = {}
            for word in self.words:
                lines.setdefault(word.line_id, []).append(word.text)
            ordered_lines = [" ".join(parts) for _, parts in sorted(lines.items())]
            text = "\n".join(ordered_lines)

        lines = {}
        for word in self.words:
            lines.setdefault(word.line_id, []).append(word)
        ordered = sorted(lines.items())
        self._line_texts = [" ".join(w.text for w in words) for _, words in ordered]

        self._full_text = text
        self._normalized_line_rects = self._compute_normalized_line_rects(
            capture, ordered, result.provider,
        )
        self._create_line_items()
        self._schedule_geometry_update()

    def set_active(self, active: bool) -> None:
        self._active = active
        for visual in self._line_visuals:
            if visual:
                visual.background.setVisible(active)
        if not active:
            self._selection_anchor = None
            self._selection_focus = None
            self._selected_chars = {}
            self._update_selection_visuals()

    def has_selection(self) -> bool:
        return any(self._selected_chars.values())

    def has_words(self) -> bool:
        return bool(self.words)

    def select_all(self) -> None:
        """Select every recognized word to mirror Snipping Tool behavior."""
        self._flush_geometry_update()
        if not self._line_texts:
            self._selected_chars = {}
            return

        self._selected_chars = {
            line_idx: set(range(len(chars)))
            for line_idx, chars in enumerate(self._char_scene_rects)
            if chars
        }
        self._selection_anchor = (0, 0)
        last_line = len(self._line_texts) - 1
        self._selection_focus = (last_line, len(self._line_texts[last_line]))
        self._update_selection_visuals()

    def clear_selection(self) -> None:
        self._selection_anchor = None
        self._selection_focus = None
        self._selected_chars = {}
        self._update_selection_visuals()

    def start_selection(self, scene_pos: QPointF, *, extend: bool = False) -> None:
        if not self._line_texts:
            return
        self._flush_geometry_update()
        caret = self._locate_caret_position(scene_pos)
        if caret is None:
            self.clear_selection()
            return
        if not extend or self._selection_anchor is None:
            self._selection_anchor = caret
            self._selected_chars = {}
        self._selection_focus = caret
        self._update_selection_from_carets()

    def update_drag(self, scene_pos: QPointF) -> None:
        if self._selection_anchor is None:
            return
        caret = self._locate_caret_position(scene_pos)
        if caret is None:
            return
        self._selection_focus = caret
        self._update_selection_from_carets()

    def finish_selection(self, scene_pos: QPointF) -> None:
        self.update_drag(scene_pos)

    def select_word_at(self, scene_pos: QPointF) -> None:
        self._flush_geometry_update()
        location = self._locate_char_position(scene_pos)
        if location is None:
            self.clear_selection()
            return
        line_idx, char_idx = location
        text = self._line_texts[line_idx]
        if not text:
            self.clear_selection()
            return

        def _kind(char: str) -> str:
            if char.isalnum() or char == "_":
                return "word"
            if char.isspace():
                return "space"
            return "punctuation"

        kind = _kind(text[char_idx])
        start = char_idx
        end = char_idx + 1
        while start > 0 and _kind(text[start - 1]) == kind:
            start -= 1
        while end < len(text) and _kind(text[end]) == kind:
            end += 1
        self._selection_anchor = (line_idx, start)
        self._selection_focus = (line_idx, end)
        self._update_selection_from_carets()

    def selected_text(self) -> str:
        if not self._selected_chars:
            return ""
        pieces = []
        for line_idx, chars in sorted(self._selected_chars.items()):
            if not chars or line_idx >= len(self._line_texts):
                continue
            text = self._line_texts[line_idx]
            ordered = sorted(chars)
            ranges: List[Tuple[int, int]] = []
            start = prev = ordered[0]
            for idx in ordered[1:]:
                if idx == prev + 1:
                    prev = idx
                    continue
                ranges.append((start, prev + 1))
                start = prev = idx
            ranges.append((start, prev + 1))

            segments = [text[a:b] for a, b in ranges if a < len(text)]
            pieces.append("".join(segments))

        return "\n".join(pieces)

    def full_text(self) -> str:
        if self._full_text:
            return self._full_text
        return " ".join(word.text for word in self.words)

    def eventFilter(self, obj, event):
        """Keep the OCR overlay aligned with the viewport and scene changes."""
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return False
        try:
            viewport = canvas.viewport()
        except RuntimeError:
            # Qt can destroy the Canvas before Python releases this filter.
            return False
        if obj is viewport and event.type() in (
                QEvent.Resize,
                QEvent.Wheel,
        ):
            self._schedule_geometry_update()
        return super().eventFilter(obj, event)

    def _on_scene_changed(self, *_args) -> None:
        if self._ignore_scene_changes:
            return
        self._schedule_geometry_update()

    def _schedule_geometry_update(self, *_args) -> None:
        if self._geometry_update_in_progress:
            self._geometry_reschedule_requested = True
            return
        if not self._geometry_timer.isActive():
            self._geometry_timer.start()

    def _flush_geometry_update(self) -> None:
        if self._geometry_update_in_progress:
            self._geometry_reschedule_requested = True
            return
        self._geometry_update_in_progress = True
        try:
            self._ignore_scene_changes = True
            self._update_geometry()
        finally:
            self._ignore_scene_changes = False
            self._geometry_update_in_progress = False
        if self._geometry_reschedule_requested:
            self._geometry_reschedule_requested = False
            self._schedule_geometry_update()

    def _current_scene_rect(self) -> Optional[QRectF]:
        if self._capture_scene_rect is None:
            return None
        if self._anchor_item and self._anchor_item.scene() == self.scene and self._anchor_local_rect is not None:
            return self._anchor_item.mapRectToScene(self._anchor_local_rect)
        return self._capture_scene_rect

    def _mapping_basis(self) -> Optional[Tuple[QRectF, bool]]:
        if self._anchor_item and self._anchor_item.scene() == self.scene and self._anchor_local_rect is not None:
            return self._anchor_local_rect, True
        if self._capture_scene_rect is not None:
            return self._capture_scene_rect, False
        return None

    def _update_geometry(self) -> None:
        mapping = self._mapping_basis()
        if mapping is None:
            return
        rect, is_local = mapping
        mapped = self._map_normalized_to_scene(rect, local=is_local)
        # Selection painting emits scene.changed too. Do not rebuild the layout
        # every 12 ms because of our own redraws; zoom uses the view transform.
        if mapped == self._scene_line_rects and len(self._char_scene_rects) == len(mapped):
            return
        self._scene_line_rects = mapped
        self._update_word_visual_geometry()
        self._update_selection_visuals()

    def _compute_normalized_line_rects(
        self, capture: OcrCapture,
        ordered_lines: List[Tuple[Tuple[int, int, int], List[OcrWord]]],
        provider: str,
    ) -> List[Optional[QRectF]]:
        px_w, px_h = capture.pixel_size
        if px_w <= 0 or px_h <= 0:
            return [None for _ in ordered_lines]
        rects: List[Optional[QRectF]] = []
        for _, words in ordered_lines:
            try:
                xs = [int(w.bbox[0]) for w in words]
                ys = [int(w.bbox[1]) for w in words]
                ws = [int(w.bbox[2]) for w in words]
                hs = [int(w.bbox[3]) for w in words]
                left = min(xs)
                top = min(ys)
                right = max(x + w for x, w in zip(xs, ws))
                bottom = max(y + h for y, h in zip(ys, hs))
                rect = QRectF(left, top, max(1.0, right - left), max(1.0, bottom - top))
                rect = rect.intersected(QRectF(0, 0, px_w, px_h))
                if rect.isEmpty():
                    rect = None
                rects.append(rect)
            except Exception:
                rects.append(None)
        groups = [line_id[:2] if provider == "mistral" else index
                  for index, (line_id, _) in enumerate(ordered_lines)]
        rects = align_line_rects(capture.image, rects, groups)
        return [QRectF(rect.left() / px_w, rect.top() / px_h,
                       rect.width() / px_w, rect.height() / px_h)
                if rect is not None else None for rect in rects]

    def _map_normalized_to_scene(self, scene_rect: QRectF, *, local: bool = False) -> List[Optional[QRectF]]:
        mapped: List[Optional[QRectF]] = []
        for rect in self._normalized_line_rects:
            if rect is None:
                mapped.append(None)
                continue
            local_rect = QRectF(
                scene_rect.left() + rect.left() * scene_rect.width(),
                scene_rect.top() + rect.top() * scene_rect.height(),
                rect.width() * scene_rect.width(),
                rect.height() * scene_rect.height(),
            )
            if local and self._anchor_item is not None:
                mapped.append(self._anchor_item.mapRectToScene(local_rect))
            else:
                mapped.append(local_rect)
        return mapped

    def _create_line_items(self) -> None:
        self._line_visuals = []
        for text in self._line_texts:
            background = QGraphicsPathItem()
            background.setZValue(9999)
            background.setAcceptedMouseButtons(Qt.NoButton)
            background.setAcceptHoverEvents(True)
            background.setCursor(Qt.IBeamCursor)

            selection = QGraphicsPathItem(background)
            selection.setAcceptedMouseButtons(Qt.NoButton)
            selection.setZValue(1)
            selection.setBrush(QColor(*Palette.OCR_TEXT_SELECTION))
            selection.setPen(Qt.NoPen)
            selection.setVisible(False)

            background.setBrush(Qt.transparent)
            background.setPen(Qt.NoPen)

            text_item = _SelectedTextItem(text, background)
            text_item.setBrush(QColor(Palette.OCR_TEXT_SELECTED_FOREGROUND))
            text_item.setPen(Qt.NoPen)
            text_item.setAcceptedMouseButtons(Qt.NoButton)
            text_item.setAcceptHoverEvents(True)
            text_item.setCursor(Qt.IBeamCursor)
            text_item.setZValue(2)

            for item in (background, selection, text_item):
                item.setData(0, "ocr_overlay")

            self.scene.addItem(background)
            self._line_visuals.append(_LineVisual(
                background=background, selection=selection,
                text_item=text_item,
            ))

    def _update_word_visual_geometry(self) -> None:
        if not self._line_visuals:
            return

        self._char_scene_rects = []
        self._caret_scene_positions = []
        for idx, visual in enumerate(self._line_visuals):
            rect = self._scene_line_rects[idx] if idx < len(self._scene_line_rects) else None
            text = self._line_texts[idx] if idx < len(self._line_texts) else ""
            if rect is None or not text:
                if visual:
                    visual.background.setVisible(False)
                    visual.selection.setVisible(False)
                self._char_scene_rects.append([])
                self._caret_scene_positions.append([])
                continue

            font = QFont(Typography.UI_FAMILY)
            font.setPixelSize(max(1, round(rect.height() * 1.35)))
            font.setHintingPreference(QFont.PreferNoHinting)
            visual.text_item.setFont(font)

            bg_path = QPainterPath()
            bg_path.addRect(QRectF(0, 0, rect.width(), rect.height()))
            visual.background.setPath(bg_path)
            visual.background.setPos(rect.left(), rect.top())
            visual.background.setVisible(self._active)

            # Fit to the visible ink height, not the provider's paragraph height
            # or the text tool's fixed 18 pt. Keep the source screenshot untouched
            # outside the selected range.
            metrics = QFontMetricsF(font)
            ink = metrics.tightBoundingRect(text).translated(0, metrics.ascent())
            scale_x = rect.width() / max(1.0, ink.width())
            scale_y = rect.height() / max(1.0, ink.height())
            visual.text_item.setTransform(QTransform.fromScale(scale_x, scale_y))
            visual.text_item.setPos(-ink.left() * scale_x, -ink.top() * scale_y)

            # Qt shapes the entire string (kerning, ligatures, surrogate pairs).
            # The same font and transform drive painting and pointer hit testing.
            layout = QTextLayout(text, font)
            layout.beginLayout()
            text_line = layout.createLine()
            text_line.setLineWidth(1e9)
            layout.endLayout()
            positions = []
            utf16_offset = 0
            for character in text:
                positions.append(text_line.cursorToX(utf16_offset)[0])
                utf16_offset += len(character.encode("utf-16-le")) // 2
            positions.append(text_line.cursorToX(utf16_offset)[0])
            positions = [max(0.0, min(rect.width(), (x - ink.left()) * scale_x))
                         for x in positions]
            self._caret_scene_positions.append([rect.left() + x for x in positions])
            line_chars: List[Optional[QRectF]] = []
            for left, right in zip(positions, positions[1:]):
                line_chars.append(QRectF(
                    rect.left() + min(left, right), rect.top(),
                    abs(right - left), rect.height(),
                ))

            self._char_scene_rects.append(line_chars)

            visual.selection.setPath(QPainterPath())
            visual.selection.setVisible(self._active)

    def _line_for_pos(self, scene_pos: QPointF) -> Optional[int]:
        candidates: List[Tuple[float, int]] = []
        for idx, rect in enumerate(self._scene_line_rects):
            if rect is None:
                continue
            if rect.contains(scene_pos):
                return idx
            distance = abs(rect.center().y() - scene_pos.y())
            candidates.append((distance, idx))
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0][1]

    def _char_index_for_pos(self, line_idx: int, scene_pos: QPointF) -> Optional[int]:
        if line_idx < 0 or line_idx >= len(self._char_scene_rects):
            return None
        chars = self._char_scene_rects[line_idx]
        if not chars:
            return None

        for idx, rect in enumerate(chars):
            if rect is not None and rect.left() <= scene_pos.x() < rect.right():
                return idx
        candidates = [(abs(rect.center().x() - scene_pos.x()), idx)
                      for idx, rect in enumerate(chars) if rect is not None]
        return min(candidates)[1] if candidates else None

    def _caret_index_for_pos(self, line_idx: int, scene_pos: QPointF) -> Optional[int]:
        if line_idx < 0 or line_idx >= len(self._caret_scene_positions):
            return None
        positions = self._caret_scene_positions[line_idx]
        if not positions:
            return None
        return min(range(len(positions)), key=lambda idx: abs(positions[idx] - scene_pos.x()))

    def _locate_char_position(self, scene_pos: QPointF) -> Optional[Tuple[int, int]]:
        line_idx = self._line_for_pos(scene_pos)
        if line_idx is None:
            return None
        char_idx = self._char_index_for_pos(line_idx, scene_pos)
        if char_idx is None:
            return None
        return line_idx, char_idx

    def _locate_caret_position(self, scene_pos: QPointF) -> Optional[Tuple[int, int]]:
        line_idx = self._line_for_pos(scene_pos)
        if line_idx is None:
            return None
        caret_idx = self._caret_index_for_pos(line_idx, scene_pos)
        if caret_idx is None:
            return None
        return line_idx, caret_idx

    def _update_selection_from_carets(self) -> None:
        if (
            not self._char_scene_rects
            or self._selection_anchor is None
            or self._selection_focus is None
        ):
            return

        start = min(self._selection_anchor, self._selection_focus)
        end = max(self._selection_anchor, self._selection_focus)
        selected: Dict[int, Set[int]] = {}
        for line_idx in range(start[0], end[0] + 1):
            if line_idx >= len(self._char_scene_rects):
                break
            char_count = len(self._char_scene_rects[line_idx])
            range_start = start[1] if line_idx == start[0] else 0
            range_end = end[1] if line_idx == end[0] else char_count
            range_start = max(0, min(range_start, char_count))
            range_end = max(0, min(range_end, char_count))
            if range_start < range_end:
                selected[line_idx] = set(range(range_start, range_end))

        self._selected_chars = selected
        self._update_selection_visuals()

    def _update_selection_visuals(self) -> None:
        if not self._line_visuals:
            return

        selected_bg = QColor(*Palette.OCR_TEXT_SELECTION)
        base_bg = Qt.transparent
        base_pen = QPen(Qt.NoPen)

        for idx, visual in enumerate(self._line_visuals):
            if visual is None:
                continue

            selection = self._selected_chars.get(idx, set())
            visual.background.setBrush(base_bg)
            visual.background.setPen(base_pen)
            visual.background.setVisible(self._active)

            visual.text_item.selection_path = QPainterPath()
            visual.text_item.setVisible(False)

            if not selection or idx >= len(self._char_scene_rects):
                visual.selection.setPath(QPainterPath())
                visual.selection.setVisible(False)
                continue

            path = QPainterPath()
            chars = self._char_scene_rects[idx]
            if not chars:
                visual.selection.setPath(path)
                visual.selection.setVisible(False)
                continue

            line_rect = self._scene_line_rects[idx]
            if line_rect is None:
                continue
            # Merge adjacent visual cells, not just logical string ranges: RTL
            # runs can put the first selected character to the right of the last.
            cells = sorted((chars[index] for index in selection
                            if index < len(chars) and chars[index] is not None
                            and chars[index].width() > 0), key=lambda cell: cell.left())
            spans: List[QRectF] = []
            for cell in cells:
                if spans and cell.left() <= spans[-1].right() + 0.01:
                    spans[-1] = spans[-1].united(cell)
                else:
                    spans.append(QRectF(cell))
            bg_pos = visual.background.pos()
            padding = min(Metrics.OCR_SELECTION_PADDING, line_rect.height() * 0.1)
            for span in spans:
                highlight_rect = span.translated(-bg_pos)
                highlight_rect.adjust(0, -padding, 0, padding)
                path.addRect(highlight_rect)

            visual.selection.setPath(path)
            visual.selection.setBrush(selected_bg)
            visual.selection.setVisible(self._active)
            visual.text_item.selection_path = path
            visual.text_item.setVisible(self._active)
            visual.text_item.update()

        self.selectionChanged.emit(self.selected_text())
