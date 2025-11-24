from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene
from PIL import Image

from design_tokens import Palette
from ocr import OcrResult, OcrWord


@dataclass
class OcrCapture:
    image: Image.Image
    scene_rect: QRectF
    pixel_size: Tuple[int, int]
    anchor_item: Optional[QGraphicsItem] = None


class OcrSelectionOverlay:
    """Overlay that maps OCR words to selectable regions on the canvas."""

    HANDLE_SIZE = 6

    def __init__(self, canvas):
        self.canvas = canvas
        self.scene: QGraphicsScene = canvas.scene
        self.words: List[OcrWord] = []
        self._word_items: List[QGraphicsRectItem] = []
        self._handle_items: List[QGraphicsRectItem] = []
        self._anchor_item: Optional[QGraphicsItem] = None
        self._active = False
        self._start_index: Optional[int] = None
        self._end_index: Optional[int] = None
        self._scale_x = 1.0
        self._scale_y = 1.0

        selection_color = QColor(*Palette.TEXT_TOOL_SELECTION)
        selection_color.setAlpha(80)
        self._selection_brush = selection_color

        outline_color = QColor(*Palette.TEXT_TOOL_SELECTION)
        outline_color.setAlpha(140)
        self._outline_pen = QPen(outline_color, 0.8)
        self._outline_pen.setCosmetic(True)

    def clear(self) -> None:
        for item in self._word_items:
            self.scene.removeItem(item)
        for item in self._handle_items:
            self.scene.removeItem(item)
        self._word_items = []
        self._handle_items = []
        self.words = []
        self._start_index = None
        self._end_index = None
        self._anchor_item = None

    def apply_result(self, result: OcrResult, capture: OcrCapture) -> None:
        self.clear()
        self.words = list(result.words)
        if not self.words:
            return

        px_w, px_h = capture.pixel_size
        if px_w <= 0 or px_h <= 0:
            return

        self._anchor_item = capture.anchor_item if capture.anchor_item and capture.anchor_item.scene() == self.scene else None

        rect = capture.scene_rect
        self._scale_x = rect.width() / float(px_w)
        self._scale_y = rect.height() / float(px_h)

        parent = self._anchor_item if self._anchor_item else None
        base_pos = QPointF(rect.left(), rect.top())
        if self._anchor_item:
            base_pos = self._anchor_item.mapFromScene(base_pos)

        line_extents = {}
        for word in self.words:
            _, y, _, h = word.bbox
            top = float(y)
            bottom = float(y + h)
            if word.line_id not in line_extents:
                line_extents[word.line_id] = [top, bottom]
            else:
                line_extents[word.line_id][0] = min(line_extents[word.line_id][0], top)
                line_extents[word.line_id][1] = max(line_extents[word.line_id][1], bottom)

        padded_extents = {}
        for line_id, (top, bottom) in line_extents.items():
            height = max(1.0, bottom - top)
            padding = max(1.0, height * 0.08)
            padded_top = max(0.0, top - padding)
            padded_bottom = min(float(px_h), bottom + padding)
            padded_extents[line_id] = (padded_top, padded_bottom)

        for word in self.words:
            x, y, w, h = word.bbox
            line_top, line_bottom = padded_extents.get(word.line_id, (y, y + h))
            mapped = QRectF(
                round(base_pos.x() + x * self._scale_x, 2),
                round(base_pos.y() + line_top * self._scale_y, 2),
                max(1.0, w * self._scale_x),
                max(1.0, (line_bottom - line_top) * self._scale_y),
            )
            item = QGraphicsRectItem(mapped, parent)
            item.setPen(self._outline_pen)
            item.setBrush(QColor(0, 0, 0, 0))
            item.setZValue((self._anchor_item.zValue() + 0.1) if self._anchor_item else 20)
            item.setVisible(self._active)
            self._word_items.append(item)

    def set_active(self, active: bool) -> None:
        self._active = active
        for item in self._word_items:
            item.setVisible(active)
        for handle in self._handle_items:
            handle.setVisible(active)
        if not active:
            self._start_index = None
            self._end_index = None

    def has_selection(self) -> bool:
        return self._start_index is not None and self._end_index is not None and self.words

    def has_words(self) -> bool:
        return bool(self.words)

    def _index_at(self, scene_pos: QPointF) -> Optional[int]:
        if not self._word_items:
            return None
        for idx, item in enumerate(self._word_items):
            if not item.isVisible():
                continue
            local = item.mapFromScene(scene_pos)
            if item.rect().contains(local):
                return idx
        return None

    def start_selection(self, scene_pos: QPointF) -> None:
        idx = self._index_at(scene_pos)
        if idx is None:
            return
        self._start_index = idx
        self._end_index = idx
        self._update_highlight()

    def update_drag(self, scene_pos: QPointF) -> None:
        if self._start_index is None:
            return
        idx = self._index_at(scene_pos)
        if idx is None:
            return
        self._end_index = idx
        self._update_highlight()

    def _selected_indices(self) -> Optional[Tuple[int, int]]:
        if self._start_index is None or self._end_index is None:
            return None
        lo = min(self._start_index, self._end_index)
        hi = max(self._start_index, self._end_index)
        return lo, hi

    def _update_highlight(self) -> None:
        indices = self._selected_indices()
        for i, item in enumerate(self._word_items):
            if indices and indices[0] <= i <= indices[1]:
                item.setBrush(self._selection_brush)
            else:
                item.setBrush(QColor(0, 0, 0, 0))

        for handle in self._handle_items:
            self.scene.removeItem(handle)
        self._handle_items = []

        if not indices:
            return

        lo, hi = indices
        first_item = self._word_items[lo]
        last_item = self._word_items[hi]
        self._handle_items = [
            self._make_handle(first_item.rect().topLeft(), first_item),
            self._make_handle(last_item.rect().bottomRight(), last_item),
        ]

    def _make_handle(self, point: QPointF, parent: QGraphicsRectItem) -> QGraphicsRectItem:
        size = self.HANDLE_SIZE
        rect = QRectF(point.x() - size / 2, point.y() - size / 2, size, size)
        handle = QGraphicsRectItem(rect, parent)
        handle.setBrush(self._selection_brush)
        handle.setPen(QPen(QColor(0, 0, 0, 0)))
        handle.setZValue(parent.zValue() + 0.2)
        handle.setVisible(self._active)
        return handle

    def selected_text(self) -> str:
        if not self.words:
            return ""
        indices = self._selected_indices()
        if not indices:
            return ""
        lo, hi = indices
        parts: List[str] = []
        prev_line = None
        for i in range(lo, hi + 1):
            word = self.words[i]
            if prev_line is not None and word.line_id != prev_line:
                parts.append("\n")
            elif i != lo:
                parts.append(" ")
            parts.append(word.text)
            prev_line = word.line_id
        return "".join(parts)

    def full_text(self) -> str:
        return " ".join(word.text for word in self.words)
