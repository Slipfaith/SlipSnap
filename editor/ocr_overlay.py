from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QPlainTextEdit
from PIL import Image

from ocr import OcrResult, OcrWord


@dataclass
class OcrCapture:
    image: Image.Image
    scene_rect: QRectF
    pixel_size: Tuple[int, int]
    anchor_item: Optional[QGraphicsItem] = None


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
        self._text_widget: Optional[QPlainTextEdit] = None
        self._selection_anchor: Optional[int] = None

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
        if self._text_widget:
            self._text_widget.hide()
            self._text_widget.deleteLater()
        self._text_widget = None

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
            # Fall back to text reconstruction from words
            lines = {}
            for word in self.words:
                lines.setdefault(word.line_id, []).append(word.text)
            ordered_lines = [" ".join(parts) for _, parts in sorted(lines.items())]
            text = "\n".join(ordered_lines)

        widget_rect = self._map_scene_rect_to_view(rect)
        if widget_rect.width() <= 0 or widget_rect.height() <= 0:
            return

        self._text_widget = self._create_text_widget()
        self._text_widget.setPlainText(text)
        self._text_widget.setGeometry(widget_rect)
        self._text_widget.setVisible(self._active)

    def set_active(self, active: bool) -> None:
        self._active = active
        if self._text_widget:
            self._text_widget.setVisible(active)
        if not active:
            self._selection_anchor = None

    def has_selection(self) -> bool:
        if self._text_widget is None:
            return False
        cursor = self._text_widget.textCursor()
        return cursor.hasSelection()

    def has_words(self) -> bool:
        return bool(self.words)

    def start_selection(self, scene_pos: QPointF) -> None:
        if self._text_widget is None:
            return
        widget_pos = self._text_widget.mapFromParent(self.canvas.mapFromScene(scene_pos))
        if not self._text_widget.rect().contains(widget_pos):
            return
        cursor = self._text_widget.cursorForPosition(widget_pos)
        self._selection_anchor = cursor.position()
        cursor.setPosition(self._selection_anchor)
        self._text_widget.setTextCursor(cursor)
        self._text_widget.setFocus(Qt.MouseFocusReason)

    def update_drag(self, scene_pos: QPointF) -> None:
        if self._selection_anchor is None or self._text_widget is None:
            return
        widget_pos = self._text_widget.mapFromParent(self.canvas.mapFromScene(scene_pos))
        if not self._text_widget.rect().contains(widget_pos):
            return
        cursor = self._text_widget.cursorForPosition(widget_pos)
        selection = QTextCursor(self._text_widget.document())
        selection.setPosition(self._selection_anchor)
        selection.setPosition(cursor.position(), QTextCursor.KeepAnchor)
        self._text_widget.setTextCursor(selection)

    def selected_text(self) -> str:
        if self._text_widget is None:
            return ""
        cursor = self._text_widget.textCursor()
        if not cursor.hasSelection():
            return ""
        return cursor.selectedText().replace("\u2029", "\n")

    def full_text(self) -> str:
        if self._text_widget is not None:
            return self._text_widget.toPlainText()
        return " ".join(word.text for word in self.words)

    def eventFilter(self, obj, event):  # noqa: D401
        """Keep the OCR overlay aligned with the viewport and scene changes."""
        if obj is self.canvas.viewport() and event.type() in (
            QEvent.Resize,
            QEvent.Paint,
            QEvent.Wheel,
        ):
            self._update_geometry()
        return super().eventFilter(obj, event)

    def _create_text_widget(self) -> QPlainTextEdit:
        if self._text_widget:
            self._text_widget.deleteLater()
        widget = QPlainTextEdit(self.canvas.viewport())
        widget.setReadOnly(True)
        widget.setFrameStyle(0)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        widget.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        widget.viewport().setAutoFillBackground(False)
        widget.setStyleSheet(
            "background: rgba(255, 255, 255, 0.85);"
            "border: 1px solid rgba(0, 0, 0, 0.08);"
            "border-radius: 8px;"
            "padding: 8px;"
        )
        widget.setFocusPolicy(Qt.ClickFocus)
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._text_widget = widget
        return widget

    def _map_scene_rect_to_view(self, rect: QRectF) -> QRect:
        top_left = self.canvas.mapFromScene(rect.topLeft())
        bottom_right = self.canvas.mapFromScene(rect.bottomRight())
        left = int(min(top_left.x(), bottom_right.x()))
        right = int(max(top_left.x(), bottom_right.x()))
        top = int(min(top_left.y(), bottom_right.y()))
        bottom = int(max(top_left.y(), bottom_right.y()))
        width = max(1, right - left)
        height = max(1, bottom - top)
        return QRect(left, top, width, height)

    def _current_scene_rect(self) -> Optional[QRectF]:
        if self._capture_scene_rect is None:
            return None
        if self._anchor_item and self._anchor_item.scene() == self.scene and self._anchor_local_rect is not None:
            return self._anchor_item.mapRectToScene(self._anchor_local_rect)
        return self._capture_scene_rect

    def _update_geometry(self) -> None:
        if self._text_widget is None:
            return
        rect = self._current_scene_rect()
        if rect is None:
            return
        widget_rect = self._map_scene_rect_to_view(rect)
        if widget_rect.width() <= 0 or widget_rect.height() <= 0:
            self._text_widget.hide()
            return
        self._text_widget.setGeometry(widget_rect)
        self._text_widget.setVisible(self._active)
