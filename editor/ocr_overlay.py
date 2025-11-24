from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
)
from PIL import Image

from editor.ui.styles import ModernColors
from ocr import OcrResult, OcrWord


@dataclass
class OcrCapture:
    image: Image.Image
    scene_rect: QRectF
    pixel_size: Tuple[int, int]
    anchor_item: Optional[QGraphicsItem] = None


@dataclass
class _WordVisual:
    background: QGraphicsPathItem  # Изменено на PathItem для скругленных углов
    text_item: QGraphicsSimpleTextItem


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
        self._word_visuals: List[Optional[_WordVisual]] = []
        self._normalized_word_rects: List[Optional[QRectF]] = []
        self._scene_word_rects: List[Optional[QRectF]] = []
        self._selected_indexes: Set[int] = set()
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
        self._selected_indexes = set()
        self._full_text = ""
        for visual in self._word_visuals:
            if visual and visual.background.scene() is self.scene:
                self.scene.removeItem(visual.background)
        self._word_visuals = []
        self._normalized_word_rects = []
        self._scene_word_rects = []

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

        self._full_text = text
        self._normalized_word_rects = self._compute_normalized_rects(capture.pixel_size)
        self._create_word_items()
        self._update_geometry()

    def set_active(self, active: bool) -> None:
        self._active = active
        for visual in self._word_visuals:
            if visual:
                visual.background.setVisible(active)
        if not active:
            self._selection_anchor = None
            self._selected_indexes = set()
            self._update_selection_visuals()

    def has_selection(self) -> bool:
        return bool(self._selected_indexes)

    def has_words(self) -> bool:
        return bool(self.words)

    def select_all(self) -> None:
        """Select every recognized word to mirror Snipping Tool behavior."""
        if not self.words:
            self._selected_indexes = set()
            return

        self._selected_indexes = {
            idx for idx, rect in enumerate(self._scene_word_rects) if rect is not None
        }
        self._update_selection_visuals()

    def start_selection(self, scene_pos: QPointF) -> None:
        if not self.words:
            return
        self._selection_anchor = scene_pos
        self._selected_indexes = set()
        self._update_selection_for_rect(QRectF(scene_pos, scene_pos))

    def update_drag(self, scene_pos: QPointF) -> None:
        if self._selection_anchor is None:
            return
        selection_rect = QRectF(self._selection_anchor, scene_pos).normalized()
        self._update_selection_for_rect(selection_rect)

    def selected_text(self) -> str:
        if not self._selected_indexes:
            return ""
        entries = []
        for idx, word in enumerate(self.words):
            if idx not in self._selected_indexes:
                continue
            rect = self._scene_word_rects[idx] if idx < len(self._scene_word_rects) else None
            entries.append((word.line_id, rect.top() if rect else 0.0, rect.left() if rect else 0.0, word.text))

        entries.sort(key=lambda item: (item[0], item[1], item[2]))

        lines: List[List[str]] = []
        current_line = None
        for line_id, _, _, text in entries:
            if current_line is None:
                current_line = line_id
                lines.append([text])
            elif line_id == current_line:
                lines[-1].append(text)
            else:
                current_line = line_id
                lines.append([text])
        return "\n".join(" ".join(parts) for parts in lines)

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
        self._scene_word_rects = self._map_normalized_to_scene(rect, local=is_local)
        self._update_word_visual_geometry()
        self._update_selection_visuals()

    def _compute_normalized_rects(self, pixel_size: Tuple[int, int]) -> List[Optional[QRectF]]:
        px_w, px_h = pixel_size
        if px_w <= 0 or px_h <= 0:
            return [None for _ in self.words]
        rects: List[Optional[QRectF]] = []
        for word in self.words:
            try:
                x, y, w, h = word.bbox
                rect = QRectF(x / px_w, y / px_h, w / px_w, h / px_h)
                rects.append(rect)
            except Exception:
                rects.append(None)
        return rects

    def _map_normalized_to_scene(self, scene_rect: QRectF, *, local: bool = False) -> List[Optional[QRectF]]:
        mapped: List[Optional[QRectF]] = []
        for rect in self._normalized_word_rects:
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

    def _create_word_items(self) -> None:
        self._word_visuals = []
        for word in self.words:
            # Используем QGraphicsPathItem для скругленных углов
            background = QGraphicsPathItem()
            background.setZValue(9999)
            background.setAcceptedMouseButtons(Qt.NoButton)

            # Полупрозрачный белый фон с тенью
            background.setBrush(QColor(255, 255, 255, 240))

            # Тонкая рамка для четкости
            pen = QPen(QColor(200, 200, 200, 100))
            pen.setWidthF(0.5)
            background.setPen(pen)

            text_item = QGraphicsSimpleTextItem(word.text, background)
            text_item.setBrush(QColor(ModernColors.TEXT_PRIMARY))
            text_item.setPen(Qt.NoPen)
            text_item.setAcceptedMouseButtons(Qt.NoButton)

            self.scene.addItem(background)
            self._word_visuals.append(_WordVisual(background=background, text_item=text_item))

    def _create_rounded_rect_path(self, rect: QRectF, radius: float) -> QPainterPath:
        """Создает путь для прямоугольника со скругленными углами."""
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _update_word_visual_geometry(self) -> None:
        if not self._word_visuals:
            return
        for idx, visual in enumerate(self._word_visuals):
            rect = self._scene_word_rects[idx] if idx < len(self._scene_word_rects) else None
            if rect is None:
                if visual:
                    visual.background.setVisible(False)
                continue

            # Увеличенный padding для лучшего вида
            padding = max(2.0, rect.height() * 0.22)
            target_height = max(8.0, rect.height() * 0.65)

            if visual is None:
                continue

            # Более четкий шрифт
            font = QFont()
            font.setPointSizeF(target_height)
            font.setWeight(QFont.Medium)  # Немного жирнее для читаемости
            font.setHintingPreference(QFont.PreferFullHinting)
            visual.text_item.setFont(font)
            text_rect = visual.text_item.boundingRect()

            available_width = max(1.0, rect.width() - 2 * padding)
            if text_rect.width() > available_width and text_rect.width() > 0:
                scale = available_width / text_rect.width()
                font.setPointSizeF(max(7.0, font.pointSizeF() * scale))
                visual.text_item.setFont(font)
                text_rect = visual.text_item.boundingRect()

            bg_width = max(rect.width(), text_rect.width() + 2 * padding)
            bg_height = max(rect.height(), text_rect.height() + 2 * padding)

            # Скругленные углы (радиус = 15% от высоты)
            radius = min(bg_height * 0.15, bg_width * 0.15, 4.0)
            rounded_path = self._create_rounded_rect_path(
                QRectF(0, 0, bg_width, bg_height),
                radius
            )
            visual.background.setPath(rounded_path)
            visual.background.setPos(rect.left(), rect.top())
            visual.background.setVisible(self._active)

            # Центрируем текст
            text_x = max(padding, (bg_width - text_rect.width()) / 2)
            text_y = max(padding, (bg_height - text_rect.height()) / 2)
            visual.text_item.setPos(text_x, text_y)

    def _update_selection_for_rect(self, selection_rect: QRectF) -> None:
        if not self._scene_word_rects:
            return
        selected = set()
        for idx, rect in enumerate(self._scene_word_rects):
            if rect is None:
                continue
            if selection_rect.isNull():
                if rect.contains(selection_rect.topLeft()):
                    selected.add(idx)
                continue
            if selection_rect.intersects(rect):
                selected.add(idx)
        self._selected_indexes = selected
        self._update_selection_visuals()

    def _update_selection_visuals(self) -> None:
        if not self._word_visuals:
            return

        # Более яркие и современные цвета для выделения
        selected_bg = QColor(ModernColors.PRIMARY_LIGHT)
        selected_bg.setAlpha(220)
        selected_fg = QColor(ModernColors.PRIMARY)

        # Улучшенные базовые цвета
        base_bg = QColor(255, 255, 255, 240)
        base_fg = QColor(ModernColors.TEXT_PRIMARY)

        for idx, visual in enumerate(self._word_visuals):
            if visual is None:
                continue
            is_selected = idx in self._selected_indexes

            visual.background.setBrush(selected_bg if is_selected else base_bg)
            visual.text_item.setBrush(selected_fg if is_selected else base_fg)

            # Изменяем границу для выделенных элементов
            if is_selected:
                pen = QPen(QColor(ModernColors.PRIMARY))
                pen.setWidthF(1.0)
                visual.background.setPen(pen)
            else:
                pen = QPen(QColor(200, 200, 200, 100))
                pen.setWidthF(0.5)
                visual.background.setPen(pen)

            visual.background.setVisible(self._active)
