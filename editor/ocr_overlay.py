from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
)
from PIL import Image

from ocr import OcrResult, OcrWord


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
    text_item: QGraphicsSimpleTextItem
    white_text: QGraphicsSimpleTextItem  # белый текст поверх выделения (clip to selection)


class OcrSelectionOverlay(QObject):
    """Overlay that maps OCR words to selectable regions on the canvas."""

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
        self._selected_chars: Dict[int, Set[int]] = {}
        self._selection_anchor: Optional[QPointF] = None
        self._full_text: str = ""

        self.canvas.viewport().installEventFilter(self)
        self.canvas.horizontalScrollBar().valueChanged.connect(self._update_geometry)
        self.canvas.verticalScrollBar().valueChanged.connect(self._update_geometry)
        self.scene.changed.connect(self._update_geometry)

    def clear(self) -> None:
        self.words = []
        self._anchor_item = None
        self._anchor_local_rect = None
        self._capture_scene_rect = None
        self._selection_anchor = None
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
        self._normalized_line_rects = self._compute_normalized_line_rects(capture.pixel_size, ordered)
        self._create_line_items()
        self._update_geometry()

    def set_active(self, active: bool) -> None:
        self._active = active
        for visual in self._line_visuals:
            if visual:
                visual.background.setVisible(active)
                visual.selection.setVisible(active)
        if not active:
            self._selection_anchor = None
            self._selected_chars = {}
            self._update_selection_visuals()

    def has_selection(self) -> bool:
        return any(self._selected_chars.values())

    def has_words(self) -> bool:
        return bool(self.words)

    def select_all(self) -> None:
        """Select every recognized word to mirror Snipping Tool behavior."""
        if not self.words:
            self._selected_chars = {}
            return

        self._selected_chars = {
            line_idx: set(range(len(chars)))
            for line_idx, chars in enumerate(self._char_scene_rects)
            if chars
        }
        self._update_selection_visuals()

    def start_selection(self, scene_pos: QPointF) -> None:
        if not self.words:
            return
        self._selection_anchor = scene_pos
        self._selected_chars = {}
        self._update_selection_for_rect(QRectF(scene_pos, scene_pos), scene_pos)

    def update_drag(self, scene_pos: QPointF) -> None:
        if self._selection_anchor is None:
            return
        selection_rect = QRectF(self._selection_anchor, scene_pos).normalized()
        self._update_selection_for_rect(selection_rect, scene_pos)

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
        if obj is self.canvas.viewport() and event.type() in (
                QEvent.Resize,
                QEvent.Paint,
                QEvent.Wheel,
        ):
            self._update_geometry()
        return super().eventFilter(obj, event)

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
        self._scene_line_rects = self._map_normalized_to_scene(rect, local=is_local)
        self._update_word_visual_geometry()
        self._update_selection_visuals()

    def _compute_normalized_line_rects(
        self, pixel_size: Tuple[int, int], ordered_lines: List[Tuple[Tuple[int, int, int], List[OcrWord]]]
    ) -> List[Optional[QRectF]]:
        px_w, px_h = pixel_size
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
                rect = QRectF(
                    left / px_w,
                    top / px_h,
                    max(1.0, right - left) / px_w,
                    max(1.0, bottom - top) / px_h,
                )
                rects.append(rect)
            except Exception:
                rects.append(None)
        return rects

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
            selection.setZValue(1)
            selection.setBrush(QColor("#0078D7"))
            selection.setPen(Qt.NoPen)
            selection.setVisible(False)
            selection.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)

            white_text = QGraphicsSimpleTextItem(text, selection)
            white_text.setBrush(QColor(Qt.white))
            white_text.setPen(Qt.NoPen)
            white_text.setAcceptedMouseButtons(Qt.NoButton)
            white_text.setAcceptHoverEvents(False)
            white_text.setZValue(1)

            background.setBrush(Qt.transparent)
            background.setPen(Qt.NoPen)

            text_item = QGraphicsSimpleTextItem(text, background)
            text_item.setBrush(Qt.transparent)
            text_item.setPen(Qt.NoPen)
            text_item.setAcceptedMouseButtons(Qt.NoButton)
            text_item.setAcceptHoverEvents(True)
            text_item.setCursor(Qt.IBeamCursor)
            text_item.setZValue(2)

            self.scene.addItem(background)
            self._line_visuals.append(_LineVisual(
                background=background, selection=selection,
                text_item=text_item, white_text=white_text,
            ))

    def _create_rounded_rect_path(self, rect: QRectF, radius: float) -> QPainterPath:
        """Создает путь для прямоугольника со скругленными углами."""
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _update_word_visual_geometry(self) -> None:
        if not self._line_visuals:
            return

        self._char_scene_rects = []
        for idx, visual in enumerate(self._line_visuals):
            rect = self._scene_line_rects[idx] if idx < len(self._scene_line_rects) else None
            text = self._line_texts[idx] if idx < len(self._line_texts) else ""
            if rect is None or not text:
                if visual:
                    visual.background.setVisible(False)
                    visual.selection.setVisible(False)
                self._char_scene_rects.append([])
                continue

            padding = 0.0
            target_height = max(9.0, rect.height() * 0.7)

            font = QFont()
            font.setPointSizeF(target_height)
            font.setWeight(QFont.Medium)
            font.setHintingPreference(QFont.PreferFullHinting)

            visual.text_item.setFont(font)
            text_rect = visual.text_item.boundingRect()

            available_width = max(1.0, rect.width() - 2 * padding)
            if text_rect.width() > 0:
                scale = available_width / text_rect.width()
                if scale < 1.0:
                    font.setPointSizeF(max(8.0, font.pointSizeF() * scale))
                    visual.text_item.setFont(font)
                    text_rect = visual.text_item.boundingRect()

                char_slots = max(len(text) - 1, 1)
                stretched_width = rect.width()
                if text_rect.width() > 0 and stretched_width > 0:
                    spacing = (stretched_width - text_rect.width()) / char_slots
                    font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
                    visual.text_item.setFont(font)
                    text_rect = visual.text_item.boundingRect()

            bg_width = max(rect.width(), text_rect.width() + 2 * padding)
            bg_height = max(rect.height(), text_rect.height() + 2 * padding)

            bg_path = QPainterPath()
            bg_path.addRect(QRectF(0, 0, bg_width, bg_height))
            visual.background.setPath(bg_path)
            visual.background.setPos(rect.left(), rect.top())
            visual.background.setVisible(self._active)

            text_x = max(padding, (bg_width - text_rect.width()) / 2)
            text_y = max(padding, (bg_height - text_rect.height()) / 2)
            visual.text_item.setPos(text_x, text_y)

            visual.white_text.setFont(font)
            visual.white_text.setPos(text_x, text_y)

            metrics = QFontMetrics(font)
            line_chars: List[Optional[QRectF]] = []
            cursor_x = rect.left() + text_x
            char_top = rect.top() + text_y
            for ch in text:
                width = metrics.horizontalAdvance(ch)
                height = metrics.height()
                char_rect = QRectF(cursor_x, char_top, max(1.0, width), max(1.0, height))
                line_chars.append(char_rect)
                cursor_x += width

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

        first_rect = next((rect for rect in chars if rect is not None), None)
        last_rect = next((rect for rect in reversed(chars) if rect is not None), None)
        if first_rect is None or last_rect is None:
            return None

        if scene_pos.x() <= first_rect.left():
            return 0
        if scene_pos.x() >= last_rect.right():
            return len(chars) - 1

        for idx, rect in enumerate(chars):
            if rect is None:
                continue
            if rect.contains(scene_pos) or scene_pos.x() <= rect.right():
                return idx
        return len(chars) - 1

    def _locate_char_position(self, scene_pos: QPointF) -> Optional[Tuple[int, int]]:
        line_idx = self._line_for_pos(scene_pos)
        if line_idx is None:
            return None
        char_idx = self._char_index_for_pos(line_idx, scene_pos)
        if char_idx is None:
            return None
        return line_idx, char_idx

    def _update_selection_for_rect(self, selection_rect: QRectF, end_pos: Optional[QPointF] = None) -> None:
        if not self._char_scene_rects or self._selection_anchor is None:
            return

        anchor_pos = self._selection_anchor
        focus_pos = end_pos or selection_rect.bottomRight()

        anchor_location = self._locate_char_position(anchor_pos)
        focus_location = self._locate_char_position(focus_pos)

        if anchor_location is None or focus_location is None:
            self._selected_chars = {}
            self._update_selection_visuals()
            return

        anchor_line, anchor_char = anchor_location
        focus_line, focus_char = focus_location

        selected: Dict[int, Set[int]] = {}

        def _select_range(line_idx: int, start_idx: int, end_idx: int) -> None:
            if line_idx < 0 or line_idx >= len(self._char_scene_rects):
                return
            chars = self._char_scene_rects[line_idx]
            if not chars:
                return
            max_idx = len(chars)
            start = max(0, min(start_idx, end_idx))
            stop = min(max_idx, max(start_idx, end_idx) + 1)
            if start < stop:
                selected[line_idx] = set(range(start, stop))

        if anchor_line == focus_line:
            _select_range(anchor_line, anchor_char, focus_char)
        else:
            step = 1 if anchor_line < focus_line else -1
            line = anchor_line
            while True:
                if line == anchor_line:
                    start_idx = anchor_char if anchor_char is not None else 0
                    _select_range(line, start_idx, len(self._char_scene_rects[line]))
                elif line == focus_line:
                    if step == 1:
                        start_idx, end_idx = 0, focus_char if focus_char is not None else len(self._char_scene_rects[line])
                    else:
                        start_idx, end_idx = focus_char if focus_char is not None else 0, len(self._char_scene_rects[line])
                    _select_range(line, start_idx, end_idx)
                else:
                    _select_range(line, 0, len(self._char_scene_rects[line]))
                if line == focus_line:
                    break
                line += step

        self._selected_chars = selected
        self._update_selection_visuals()

    def _update_selection_visuals(self) -> None:
        if not self._line_visuals:
            return

        selected_bg = QColor("#0078D7")
        base_bg = Qt.transparent
        base_pen = QPen(Qt.NoPen)

        for idx, visual in enumerate(self._line_visuals):
            if visual is None:
                continue

            selection = self._selected_chars.get(idx, set())
            visual.background.setBrush(base_bg)
            visual.background.setPen(base_pen)
            visual.background.setVisible(self._active)

            visual.text_item.setBrush(Qt.transparent)

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

            ordered = sorted(selection)
            start = prev = ordered[0]
            ranges: List[Tuple[int, int]] = []
            for char_idx in ordered[1:]:
                if char_idx == prev + 1:
                    prev = char_idx
                    continue
                ranges.append((start, prev))
                start = prev = char_idx
            ranges.append((start, prev))

            for a, b in ranges:
                if a >= len(chars) or chars[a] is None:
                    continue
                left = chars[a].left()
                top = chars[a].top()
                right = chars[b].right() if b < len(chars) and chars[b] is not None else left
                height = chars[a].height()
                bg_pos = visual.background.pos()
                highlight_rect = QRectF(
                    left - bg_pos.x(),
                    top - bg_pos.y(),
                    max(1.0, right - left),
                    height,
                )
                path.addRect(highlight_rect)

            visual.selection.setPath(path)
            visual.selection.setBrush(selected_bg)
            visual.selection.setVisible(self._active)
