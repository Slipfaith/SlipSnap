from typing import Optional, Dict, Tuple
from pathlib import Path
import tempfile
import shutil
import math

from PySide6.QtCore import (
    Qt,
    QPointF,
    QRectF,
    QPoint,
    QRect,
    Signal,
    QMarginsF,
    QEasingCurve,
    QVariantAnimation,
    QAbstractAnimation,
    QMimeData,
    QUrl,
    QLineF,
    QTimer,
    QElapsedTimer,
)
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QImage,
    QMovie,
    QUndoStack,
    QLinearGradient,
    QBrush,
    QPainterPath,
    QDrag,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsItem,
    QGraphicsTextItem,
    QGraphicsLineItem,
    QGraphicsItemGroup,
    QMenu,
    QMessageBox,
    QFrame,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsDropShadowEffect,
    QApplication,
)
from PIL import Image, ImageSequence

from .styles import ModernColors
from .high_quality_pixmap_item import HighQualityPixmapItem
from .icon_factory import create_pencil_cursor, create_select_cursor
from .zoom_lens_item import ZoomLensItem
from logic import qimage_to_pil, save_config
from editor.text_tools import EditableTextItem, TextManager
from editor.ocr_overlay import OcrSelectionOverlay, OcrCapture
from editor.tools.selection_tool import SelectionTool
from editor.tools.pencil_tool import PencilTool
from editor.tools.shape_tools import RectangleTool, EllipseTool
from editor.tools.blur_tool import BlurTool
from editor.tools.eraser_tool import EraserTool
from editor.tools.line_arrow_tool import LineTool, ArrowTool
from editor.undo_commands import AddCommand, MoveCommand, ResizeCommand, ScaleCommand, ZValueCommand, RemoveCommand, RotateCommand
from editor.image_utils import images_from_mime
from meme_library import save_meme_image

from design_tokens import Metrics

MARKER_ALPHA = Metrics.MARKER_ALPHA
PENCIL_WIDTH = Metrics.PENCIL_WIDTH
MARKER_WIDTH = Metrics.MARKER_WIDTH

ITEM_ANIMATION_ROLE = 9
ANIMATION_NONE = "none"
ANIMATION_DRAW = "draw"
ANIMATION_PULSE = "pulse"
ANIMATION_DRAW_ACTIVE_MS = 1200
ANIMATION_DRAW_HOLD_MS = 1500
ANIMATION_DRAW_CYCLE_MS = ANIMATION_DRAW_ACTIVE_MS + ANIMATION_DRAW_HOLD_MS
ANIMATION_PULSE_CYCLE_MS = 1000
ANIMATION_PULSE_MAX_DIMENSION = 220.0
ANIMATION_PULSE_MAX_AREA = 24000.0


class Canvas(QGraphicsView):
    """Drawing canvas holding the image and drawn items."""

    imageDropped = Signal(QImage)
    toolChanged = Signal(str)
    zoomChanged = Signal(float)  # emitted when zoom changes (factor 0.1–4.0)

    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        # Force full repaints while dragging items to avoid visual ghosting
        # when the selection is moved.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        self.pixmap_item: Optional[HighQualityPixmapItem] = HighQualityPixmapItem(image)
        self.pil_image = qimage_to_pil(image)  # store original PIL image
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.pixmap_item.setData(0, "screenshot")
        self.pixmap_item.setData(1, "base")
        self.scene.addItem(self.pixmap_item)

        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.setStyleSheet(f"""
            QGraphicsView {{
                background: {ModernColors.SURFACE_VARIANT};
                border: none;
                padding: 0;
            }}
            QGraphicsView:focus {{
                border: none;
                outline: none;
            }}
        """)

        self._tool = "select"
        self._pen_mode = "pencil"
        self._base_pen_color = QColor(ModernColors.PRIMARY)
        self._pen = QPen(self._base_pen_color, PENCIL_WIDTH)
        self._pen.setCapStyle(Qt.RoundCap)
        self._pen.setJoinStyle(Qt.RoundJoin)
        self._apply_pen_mode()
        self.undo_stack = QUndoStack(self)
        self._move_snapshot: Dict[QGraphicsItem, QPointF] = {}
        self._text_manager: Optional[TextManager] = None
        self._zoom = 1.0
        self.ocr_overlay = OcrSelectionOverlay(self)
        self._ocr_scan_bar: Optional[QGraphicsPathItem] = None
        self._ocr_scan_dim: Optional[QGraphicsRectItem] = None
        self._ocr_scan_anim = None
        self._ocr_scan_fade = None
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_temp_dirs: list[Path] = []
        self._dragging_external = False
        self._zoom_lens_cursor_vp: Optional[QPoint] = None
        self._zoom_lens_radius_px: int = 90
        self._zoom_lens_factor: float = 2.0
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self.tools = {
            "select": SelectionTool(self),
            "free": PencilTool(self),
            "rect": RectangleTool(self),
            "ellipse": EllipseTool(self),
            "line": LineTool(self),
            "arrow": ArrowTool(self),
            "blur": BlurTool(self, ModernColors.PRIMARY),
            "erase": EraserTool(self),
        }
        self.active_tool = self.tools["select"]

        self._pencil_cursor = create_pencil_cursor()
        self._select_cursor = create_select_cursor()
        self._apply_lock_state()
        self.update_scene_rect()
        if self.pixmap_item:
            self.centerOn(self.pixmap_item)

        # Corner-handle resize state
        self._corner_resize: Optional[dict] = None
        # Rotation drag state
        self._rotation_drag: Optional[dict] = None
        # Live preview state for item animations in editor viewport.
        self._live_item_animations: list[dict] = []
        self._suspend_live_item_animation = False
        self._item_animation_elapsed = QElapsedTimer()
        self._item_animation_timer = QTimer(self)
        self._item_animation_timer.setInterval(33)
        self._item_animation_timer.timeout.connect(self._on_item_animation_tick)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        super().drawForeground(painter, rect)
        selected = [it for it in self.scene.selectedItems() if it.isVisible()]
        if selected:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, False)  # crisp lines

        if selected:
            scale = abs(self.transform().m11()) or 1.0
            scale = max(scale, 1e-3)

            border = QColor(ModernColors.PRIMARY)
            border.setAlpha(190)

            handle_border = QColor(ModernColors.PRIMARY)
            handle_border.setAlpha(210)
            handle_fill = QColor(255, 255, 255, 245)

            for item in selected:
                # While the user is typing inside a text item Qt already draws its
                # own selection highlight - skip our overlay to avoid confusion.
                if isinstance(item, EditableTextItem) and getattr(item, "_is_editing", False):
                    continue

                padding = 3.0 / scale
                sr = item.sceneBoundingRect().adjusted(-padding, -padding, padding, padding)

                # Thin solid border, no fill
                pen = QPen(border, 1.0)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(sr)

                # Small square handles at four corners
                h = 4.0 / scale
                pen2 = QPen(handle_border, 1.0)
                pen2.setCosmetic(True)
                painter.setPen(pen2)
                painter.setBrush(QBrush(handle_fill))
                for corner in (sr.topLeft(), sr.topRight(), sr.bottomLeft(), sr.bottomRight()):
                    painter.drawRect(QRectF(corner.x() - h, corner.y() - h, h * 2, h * 2))

                # Rotation handle - circle above top-center connected by a stem line
                rot_offset = 28.0 / scale
                rot_r = 5.0 / scale
                top_center = QPointF(sr.center().x(), sr.top())
                rot_pt = QPointF(top_center.x(), top_center.y() - rot_offset)

                stem_pen = QPen(border, 1.0)
                stem_pen.setCosmetic(True)
                painter.setPen(stem_pen)
                painter.setBrush(Qt.NoBrush)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.drawLine(top_center, rot_pt)

                rot_pen = QPen(handle_border, 1.5)
                rot_pen.setCosmetic(True)
                painter.setPen(rot_pen)
                painter.setBrush(QBrush(handle_fill))
                painter.drawEllipse(rot_pt, rot_r, rot_r)
                painter.setRenderHint(QPainter.Antialiasing, False)

            painter.restore()

        self._draw_zoom_lens_overlay(painter)

    def _zoom_lens_items(self, only_items=None) -> list[ZoomLensItem]:
        allowed = self._expanded_item_set(only_items) if only_items is not None else None
        items: list[ZoomLensItem] = []
        for item in self.scene.items():
            if not isinstance(item, ZoomLensItem):
                continue
            if not item.isVisible():
                continue
            if allowed is not None and item not in allowed:
                continue
            items.append(item)
        items.sort(key=lambda it: (it.zValue(), id(it)))
        return items

    def _selected_zoom_lens_items(self) -> list[ZoomLensItem]:
        selected: list[ZoomLensItem] = []
        for item in self.scene.selectedItems():
            if isinstance(item, ZoomLensItem):
                selected.append(item)
        return selected

    def _zoom_lens_item_at(self, scene_pos: QPointF) -> Optional[ZoomLensItem]:
        for item in self.scene.items(scene_pos):
            if isinstance(item, ZoomLensItem):
                return item
        return None

    def _draw_single_zoom_lens_overlay(
        self,
        painter: QPainter,
        source_img: QImage,
        center_px: QPointF,
        radius_px: float,
        zoom_factor: float,
    ) -> None:
        radius = max(2.0, float(radius_px))
        lens_zoom = max(1.2, float(zoom_factor))
        lens_rect = QRectF(center_px.x() - radius, center_px.y() - radius, radius * 2.0, radius * 2.0)
        if lens_rect.width() < 2 or lens_rect.height() < 2:
            return

        src_half = max(1.0, radius / lens_zoom)
        src_rect = QRectF(center_px.x() - src_half, center_px.y() - src_half, src_half * 2.0, src_half * 2.0)

        clip = QPainterPath()
        clip.addEllipse(lens_rect)
        painter.save()
        painter.setClipPath(clip)
        painter.drawImage(lens_rect, source_img, src_rect)
        painter.setClipping(False)

        outer_ring = QPen(QColor(25, 30, 38, 210), 3)
        outer_ring.setCosmetic(True)
        painter.setPen(outer_ring)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(lens_rect)

        inner_ring = QPen(QColor(255, 255, 255, 220), 1.5)
        inner_ring.setCosmetic(True)
        painter.setPen(inner_ring)
        painter.drawEllipse(lens_rect.adjusted(2, 2, -2, -2))

        cross_pen = QPen(QColor(255, 255, 255, 180), 1)
        cross_pen.setCosmetic(True)
        painter.setPen(cross_pen)
        painter.drawLine(
            QPointF(center_px.x() - 8, center_px.y()),
            QPointF(center_px.x() + 8, center_px.y()),
        )
        painter.drawLine(
            QPointF(center_px.x(), center_px.y() - 8),
            QPointF(center_px.x(), center_px.y() + 8),
        )

        painter.restore()

    def _draw_zoom_lens_overlay(self, painter: QPainter) -> None:
        lens_items = self._zoom_lens_items()
        show_preview = self._tool == "zoom_lens" and self._zoom_lens_cursor_vp is not None
        if not lens_items and not show_preview:
            return

        viewport_rect = QRectF(self.viewport().rect())
        if viewport_rect.width() <= 1 or viewport_rect.height() <= 1:
            return

        source_scene = self.mapToScene(self.viewport().rect()).boundingRect()
        source_img = QImage(
            int(max(1, viewport_rect.width())),
            int(max(1, viewport_rect.height())),
            QImage.Format_ARGB32_Premultiplied,
        )
        source_img.fill(Qt.transparent)
        source_painter = QPainter(source_img)
        source_painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene.render(
            source_painter,
            QRectF(0, 0, source_img.width(), source_img.height()),
            source_scene,
            Qt.IgnoreAspectRatio,
        )
        source_painter.end()

        view_zoom = max(abs(self.transform().m11()), 1e-3)
        painter.save()
        painter.resetTransform()  # draw in viewport pixels, independent from scene zoom
        for lens in lens_items:
            center_scene = lens.mapToScene(lens.boundingRect().center())
            center_vp_i = self.mapFromScene(center_scene)
            center_vp = QPointF(float(center_vp_i.x()), float(center_vp_i.y()))
            radius_vp = float(lens.effective_radius_scene()) * view_zoom
            self._draw_single_zoom_lens_overlay(
                painter,
                source_img,
                center_vp,
                radius_vp,
                lens.zoom_factor(),
            )

        if show_preview and self._zoom_lens_cursor_vp is not None:
            center_vp = QPointF(float(self._zoom_lens_cursor_vp.x()), float(self._zoom_lens_cursor_vp.y()))
            radius_vp = float(self._zoom_lens_radius_px) * view_zoom
            self._draw_single_zoom_lens_overlay(
                painter,
                source_img,
                center_vp,
                radius_vp,
                self._zoom_lens_factor,
            )
        painter.restore()

    def _apply_zoom_lenses_to_image(self, image: QImage, rect: QRectF, dpr: float, only_items=None) -> None:
        lens_items = self._zoom_lens_items(only_items=only_items)
        if not lens_items:
            return
        source_img = image.copy()
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        for lens in lens_items:
            center_scene = lens.mapToScene(lens.boundingRect().center())
            center_px = QPointF(
                (center_scene.x() - rect.left()) * dpr,
                (center_scene.y() - rect.top()) * dpr,
            )
            radius_px = float(lens.effective_radius_scene()) * dpr
            self._draw_single_zoom_lens_overlay(
                painter,
                source_img,
                center_px,
                radius_px,
                lens.zoom_factor(),
            )
        painter.end()

    def _persist_zoom_lens_settings(self) -> None:
        win = self.window()
        cfg = getattr(win, "cfg", None)
        if not isinstance(cfg, dict):
            return
        cfg["zoom_lens_size"] = int(self._zoom_lens_radius_px)
        cfg["zoom_lens_factor"] = round(float(self._zoom_lens_factor), 2)
        try:
            save_config(cfg)
        except Exception:
            pass

    def _show_zoom_lens_context_menu(self, global_pos: QPoint, lens: Optional[ZoomLensItem] = None) -> None:
        menu = QMenu(self)
        zoom_actions: dict = {}
        current_factor = lens.zoom_factor() if lens is not None else float(self._zoom_lens_factor)
        for factor in (1.5, 2.0, 2.5, 3.0, 4.0, 6.0):
            act = menu.addAction(f"{factor:.1f}x")
            act.setCheckable(True)
            act.setChecked(abs(current_factor - factor) < 0.05)
            zoom_actions[act] = factor
        chosen = menu.exec(global_pos)
        if chosen in zoom_actions:
            new_factor = max(1.2, min(8.0, float(zoom_actions[chosen])))
            self._zoom_lens_factor = new_factor
            if lens is not None:
                lens.set_zoom_factor(new_factor)
            self._persist_zoom_lens_settings()
            self.viewport().update()

    def add_zoom_lens_item(
        self,
        scene_pos: QPointF,
        *,
        radius_px: Optional[int] = None,
        zoom_factor: Optional[float] = None,
    ) -> ZoomLensItem:
        lens = ZoomLensItem(
            radius_px=self._zoom_lens_radius_px if radius_px is None else int(radius_px),
            zoom_factor=self._zoom_lens_factor if zoom_factor is None else float(zoom_factor),
        )
        lens.setPos(scene_pos)
        self.scene.addItem(lens)
        self.undo_stack.push(AddCommand(self.scene, lens))
        self.bring_to_front(lens, record=False)
        self.scene.clearSelection()
        lens.setSelected(True)
        self.viewport().update()
        return lens

    # ---- drag & drop ----
    def dragEnterEvent(self, event):
        if images_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if images_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        images = images_from_mime(event.mimeData())
        if not images:
            event.ignore()
            return

        for qimg in images:
            self.imageDropped.emit(qimg)
        event.acceptProposedAction()

    def _should_start_external_drag(self, event) -> bool:
        if self._drag_start_pos is None or self._dragging_external:
            return False
        if not (self.scene.selectedItems() or self.pixmap_item):
            return False
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < QApplication.startDragDistance():
            return False
        viewport_rect = self.viewport().rect()
        top_left = self.viewport().mapToGlobal(viewport_rect.topLeft())
        bottom_right = self.viewport().mapToGlobal(viewport_rect.bottomRight())
        global_rect = QRect(top_left, bottom_right)
        return not global_rect.contains(event.globalPosition().toPoint())

    def _export_drag_image(self) -> Image.Image:
        if self.scene.selectedItems():
            return self.export_selection()
        return self.export_image()

    def _normalized_animation_kind(self, kind) -> str:
        raw = str(kind or "").strip().lower()
        if raw in {ANIMATION_DRAW, ANIMATION_PULSE}:
            return raw
        return ANIMATION_NONE

    def _item_animation_kind(self, item: QGraphicsItem) -> str:
        try:
            return self._normalized_animation_kind(item.data(ITEM_ANIMATION_ROLE))
        except Exception:
            return ANIMATION_NONE

    def _set_item_animation_kind(self, item: QGraphicsItem, kind: str) -> bool:
        normalized = self._normalized_animation_kind(kind)
        if self._item_animation_kind(item) == normalized:
            return False
        item.setData(ITEM_ANIMATION_ROLE, normalized)
        self._refresh_live_item_animation_state()
        return True

    def _stop_live_item_animation(self) -> None:
        if self._item_animation_timer.isActive():
            self._item_animation_timer.stop()
        if self._live_item_animations:
            self._restore_item_animations(self._live_item_animations)
            self._live_item_animations = []
            self.viewport().update()

    def _refresh_live_item_animation_state(self) -> None:
        if self._suspend_live_item_animation:
            return
        has_live = bool(self._relevant_item_animations())
        if has_live:
            if not self._item_animation_elapsed.isValid():
                self._item_animation_elapsed.start()
            if not self._item_animation_timer.isActive():
                self._item_animation_timer.start()
        else:
            self._stop_live_item_animation()

    def _on_item_animation_tick(self) -> None:
        if self._suspend_live_item_animation:
            return
        if QApplication.mouseButtons() != Qt.NoButton:
            # Do not animate while the user drags/resizes items.
            if self._live_item_animations:
                self._restore_item_animations(self._live_item_animations)
                self._live_item_animations = []
                self.viewport().update()
            return

        if self._live_item_animations:
            self._restore_item_animations(self._live_item_animations)
            self._live_item_animations = []

        states = self._relevant_item_animations()
        if not states:
            self._stop_live_item_animation()
            return

        if not self._item_animation_elapsed.isValid():
            self._item_animation_elapsed.start()
        time_ms = int(self._item_animation_elapsed.elapsed())
        self._apply_item_animations_at(states, time_ms)
        self._live_item_animations = states
        self.viewport().update()

    def _can_animate_item(self, item: QGraphicsItem) -> bool:
        if item is None or item.scene() != self.scene:
            return False
        if isinstance(item, ZoomLensItem):
            return False
        if item.data(1) == "base":
            return False
        if not item.isVisible():
            return False
        if not bool(item.flags() & QGraphicsItem.ItemIsSelectable):
            return False
        return True

    def _is_pulse_eligible(self, item: QGraphicsItem) -> bool:
        if not self._can_animate_item(item):
            return False
        rect = item.sceneBoundingRect()
        if rect.isNull():
            return False
        width = max(0.0, float(rect.width()))
        height = max(0.0, float(rect.height()))
        if max(width, height) > ANIMATION_PULSE_MAX_DIMENSION:
            return False
        if (width * height) > ANIMATION_PULSE_MAX_AREA:
            return False
        return True

    def _draw_animation_segments(self, item: QGraphicsItem) -> list[dict]:
        segments: list[dict] = []
        if isinstance(item, QGraphicsLineItem):
            line = QLineF(item.line())
            segments.append(
                {
                    "item": item,
                    "line": line,
                    "length": max(0.0, line.length()),
                    "opacity": float(item.opacity()),
                }
            )
            return segments

        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                if isinstance(child, QGraphicsLineItem):
                    line = QLineF(child.line())
                    segments.append(
                        {
                            "item": child,
                            "line": line,
                            "length": max(0.0, line.length()),
                            "opacity": float(child.opacity()),
                        }
                    )
        return segments

    def _relevant_item_animations(self, only_items=None) -> list[dict]:
        allowed = self._expanded_item_set(only_items) if only_items is not None else None
        animations: list[dict] = []
        for item in self.scene.items():
            if allowed is not None and item not in allowed:
                continue
            if not self._can_animate_item(item):
                continue
            kind = self._item_animation_kind(item)
            if kind == ANIMATION_NONE:
                continue
            state = {
                "item": item,
                "kind": kind,
                "base_scale": float(item.scale()),
                "base_opacity": float(item.opacity()),
            }
            if kind == ANIMATION_DRAW:
                state["cycle_ms"] = ANIMATION_DRAW_CYCLE_MS
                state["draw_active_ms"] = ANIMATION_DRAW_ACTIVE_MS
                segments = self._draw_animation_segments(item)
                total_len = sum(seg["length"] for seg in segments)
                if total_len > 1e-3:
                    state["mode"] = "segments"
                    state["segments"] = segments
                    state["total_len"] = total_len
                else:
                    state["mode"] = "fade"
            elif kind == ANIMATION_PULSE:
                if not self._is_pulse_eligible(item):
                    continue
                state["cycle_ms"] = ANIMATION_PULSE_CYCLE_MS
                state["mode"] = "pulse"
            animations.append(state)
        return animations

    def _apply_item_animations_at(self, animations: list[dict], time_ms: int) -> None:
        for state in animations:
            item = state["item"]
            mode = state.get("mode")
            cycle_ms = max(1, int(state.get("cycle_ms", ANIMATION_PULSE_CYCLE_MS)))
            t_mod = int(time_ms) % cycle_ms
            phase = t_mod / float(cycle_ms)
            draw_active_ms = max(1, int(state.get("draw_active_ms", ANIMATION_DRAW_ACTIVE_MS)))
            draw_progress = 1.0 if t_mod >= draw_active_ms else (t_mod / float(draw_active_ms))

            if mode == "pulse":
                base_scale = float(state["base_scale"])
                pulse = 1.0 + 0.05 * math.sin(math.pi * phase)
                item.setScale(base_scale * pulse)
                item.setOpacity(float(state["base_opacity"]))
                continue

            if mode == "segments":
                total = max(1e-6, float(state.get("total_len", 0.0)))
                remaining = total * draw_progress
                for seg in state.get("segments", []):
                    seg_item = seg["item"]
                    base_line: QLineF = seg["line"]
                    seg_len = max(0.0, float(seg["length"]))
                    start = base_line.p1()
                    end = base_line.p2()
                    if remaining <= 0.0:
                        seg_item.setLine(QLineF(start, start))
                    elif remaining >= seg_len:
                        seg_item.setLine(QLineF(start, end))
                    else:
                        ratio = remaining / max(seg_len, 1e-6)
                        current = QPointF(
                            start.x() + (end.x() - start.x()) * ratio,
                            start.y() + (end.y() - start.y()) * ratio,
                        )
                        seg_item.setLine(QLineF(start, current))
                    seg_item.setOpacity(float(seg["opacity"]))
                    remaining -= seg_len
                item.setScale(float(state["base_scale"]))
                item.setOpacity(float(state["base_opacity"]))
                continue

            # Generic draw fallback for non-line items: fade-in.
            if state.get("kind") == ANIMATION_DRAW:
                item.setOpacity(max(0.0, min(1.0, float(state["base_opacity"]) * draw_progress)))
                item.setScale(float(state["base_scale"]))
            else:
                item.setOpacity(float(state["base_opacity"]))
                item.setScale(float(state["base_scale"]))

    def _restore_item_animations(self, animations: list[dict]) -> None:
        for state in animations:
            item = state["item"]
            try:
                item.setScale(float(state["base_scale"]))
                item.setOpacity(float(state["base_opacity"]))
            except Exception:
                pass
            for seg in state.get("segments", []):
                seg_item = seg["item"]
                try:
                    seg_item.setLine(QLineF(seg["line"]))
                    seg_item.setOpacity(float(seg["opacity"]))
                except Exception:
                    pass

    def _has_item_animations(self) -> bool:
        return bool(self._relevant_item_animations())

    def has_gif_content(self) -> bool:
        for item in self.scene.items():
            if str(item.data(1)).lower() == "gif":
                return True
        return self._has_item_animations()

    def _effective_drag_extension(self) -> str:
        return ".gif" if self.has_gif_content() else ".png"

    def _next_drag_filename(self) -> str:
        win = self.window()
        logic = getattr(win, "logic", None)
        target_dir = self._detect_external_drop_directory()
        extension = self._effective_drag_extension()
        if logic and hasattr(logic, "next_snap_filename"):
            if target_dir is not None and hasattr(logic, "next_snap_filename_for_directory"):
                try:
                    return logic.next_snap_filename_for_directory(target_dir, extension=extension)
                except TypeError:
                    return logic.next_snap_filename_for_directory(target_dir)
                except Exception:
                    pass
            try:
                return logic.next_snap_filename(extension=extension)
            except TypeError:
                return logic.next_snap_filename()
        return f"snap_01{extension}"

    def _detect_external_drop_directory(self) -> Optional[Path]:
        """Best-effort detection of Explorer folder under cursor on Windows."""
        try:
            import win32con
            import win32gui
            import win32com.client
            from win32com.shell import shell, shellcon
        except Exception:
            return None

        try:
            cursor_pos = win32gui.GetCursorPos()
            hwnd = win32gui.WindowFromPoint(cursor_pos)
            if not hwnd:
                return None
            root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
            if not root_hwnd:
                root_hwnd = hwnd
        except Exception:
            return None

        try:
            shell_app = win32com.client.Dispatch("Shell.Application")
            for window in shell_app.Windows():
                try:
                    if int(window.HWND) != int(root_hwnd):
                        continue
                    folder = window.Document.Folder
                    if folder is None:
                        continue
                    folder_path = str(folder.Self.Path or "").strip()
                    if not folder_path or folder_path.startswith("::"):
                        continue
                    candidate = Path(folder_path)
                    if candidate.is_dir():
                        return candidate
                except Exception:
                    continue
        except Exception:
            pass

        # Desktop icons can come from Progman/WorkerW and are not always listed.
        try:
            class_name = win32gui.GetClassName(root_hwnd)
            if class_name in {"Progman", "WorkerW"}:
                desktop = shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, 0, 0)
                candidate = Path(desktop)
                if candidate.is_dir():
                    return candidate
        except Exception:
            pass

        return None

    def _start_external_drag(self) -> None:
        if self._move_snapshot:
            for item, pos in self._move_snapshot.items():
                item.setPos(pos)
            self._move_snapshot = {}
        filename = self._next_drag_filename()
        drag_dir = Path(tempfile.mkdtemp(prefix="slipsnap_drag_"))
        self._drag_temp_dirs.append(drag_dir)
        use_gif = self._effective_drag_extension() == ".gif"
        target = drag_dir / filename
        target = target.with_suffix(".gif" if use_gif else ".png")
        if use_gif:
            saved = self.save_animated_gif(target, selected_only=bool(self.scene.selectedItems()))
            if not saved:
                image = self._export_drag_image()
                if image is None:
                    return
                image.save(target, format="GIF")
        else:
            image = self._export_drag_image()
            if image is None:
                return
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            image.save(target, format="PNG")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(target))])
        drag = QDrag(self.viewport())
        drag.setMimeData(mime)
        self._dragging_external = True
        drag.exec(Qt.CopyAction)
        self._dragging_external = False

    def _cleanup_temp_dirs(self) -> None:
        """Remove accumulated drag-and-drop temp directories."""
        for d in self._drag_temp_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        self._drag_temp_dirs.clear()

    def _set_pixmap_items_interactive(self, enabled: bool):
        for it in self.scene.items():
            if isinstance(it, QGraphicsPixmapItem) or it.data(0) == "blur":
                it.setFlag(QGraphicsItem.ItemIsMovable, enabled)
                it.setFlag(QGraphicsItem.ItemIsSelectable, True)
                it.setAcceptedMouseButtons(Qt.AllButtons if enabled else Qt.NoButton)
                if not enabled and it.isSelected():
                    it.setSelected(False)

    def _apply_lock_state(self):
        lock = self._tool not in ("none", "select")
        self._set_pixmap_items_interactive(not lock)
        if self._tool == "select":
            self.setDragMode(QGraphicsView.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.NoDrag)

    def set_base_image(self, image: QImage):
        """Replace the main screenshot and clear existing items."""
        self._cleanup_temp_dirs()
        self._stop_live_item_animation()
        self.scene.clear()
        self.ocr_overlay.clear()
        self.pixmap_item = HighQualityPixmapItem(image)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.pixmap_item.setData(0, "screenshot")
        self.pixmap_item.setData(1, "base")
        self.scene.addItem(self.pixmap_item)
        self.pil_image = qimage_to_pil(image)
        self.undo_stack.clear()
        if self._text_manager:
            self._text_manager.finish_current_editing()
        self._apply_lock_state()
        self.hide_ocr_scanner()
        # Reset the scene rect so update_scene_rect starts fresh (not expanded
        # from a previous, possibly much larger, session rect).
        self.scene.setSceneRect(QRectF())
        self.update_scene_rect()
        # Centre on the new screenshot exactly once at load time.
        if self.pixmap_item:
            self.centerOn(self.pixmap_item)

    def handle_item_removed(self, item: QGraphicsItem) -> None:
        if item is self.pixmap_item or item.data(1) == "base":
            self.pixmap_item = None
            self.pil_image = None
        self._refresh_live_item_animation_state()

    def handle_item_restored(self, item: QGraphicsItem) -> None:
        if isinstance(item, QGraphicsPixmapItem) and item.data(1) == "base":
            self.pixmap_item = item
            qimg = item.pixmap().toImage()
            if not qimg.isNull():
                self.pil_image = qimage_to_pil(qimg)
            if isinstance(item, HighQualityPixmapItem):
                item.reset_scale_tracking()
        self._refresh_live_item_animation_state()

    def set_tool(self, tool: str):
        if self._text_manager:
            self._text_manager.finish_current_editing()

        previous_tool = self._tool
        self._tool = tool
        self.active_tool = self.tools.get(tool)

        if tool == "select":
            self.viewport().setCursor(self._select_cursor)
        elif tool == "erase":
            if self.active_tool and hasattr(self.active_tool, 'cursor'):
                self.viewport().setCursor(self.active_tool.cursor)
            else:
                self.viewport().setCursor(Qt.ArrowCursor)
        elif tool in {"rect", "ellipse", "line", "arrow", "blur"}:
            self.viewport().setCursor(Qt.CrossCursor)
        elif tool == "free":
            self.viewport().setCursor(self._pencil_cursor)
        elif tool == "text":
            self.viewport().setCursor(Qt.IBeamCursor)
        elif tool == "ocr":
            self.viewport().setCursor(Qt.IBeamCursor)
        elif tool == "zoom_lens":
            self.viewport().setCursor(Qt.CrossCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

        if hasattr(self, "ocr_overlay"):
            self.ocr_overlay.set_active(tool == "ocr")
        if tool == "zoom_lens":
            if self._zoom_lens_cursor_vp is None:
                self._zoom_lens_cursor_vp = self.viewport().rect().center()
        else:
            self._zoom_lens_cursor_vp = None
        if tool == "zoom_lens" or previous_tool == "zoom_lens":
            self.viewport().update()
        self.toolChanged.emit(tool)
        self._apply_lock_state()

    # ---- scene management ----
    def update_scene_rect(self) -> None:
        """Set a generous scene rect around the current content.

        Called once when a screenshot is loaded.  Never called during editing
        so the viewport is never moved by this method.
        """
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 0, 0)
        # Give plenty of room on every side so the user can freely place items
        # and pan without needing further scene-rect updates.
        pad = max(rect.width(), rect.height(), 800.0)
        self.scene.setSceneRect(rect.marginsAdded(QMarginsF(pad, pad, pad, pad)))

    def set_text_manager(self, text_manager: TextManager):
        self._text_manager = text_manager

    def set_pen_width(self, w: int):
        self._pen.setWidth(w)

    def set_pen_color(self, color: QColor):
        self._base_pen_color = QColor(color)
        self._apply_pen_mode()

    def set_pen_mode(self, mode: str):
        self._pen_mode = mode
        self._apply_pen_mode()

    @property
    def pen_mode(self) -> str:
        return self._pen_mode

    def _apply_pen_mode(self):
        color = QColor(self._base_pen_color)
        if self._pen_mode == "marker":
            color.setAlpha(MARKER_ALPHA)
            self._pen.setWidth(MARKER_WIDTH)
        else:
            color.setAlpha(255)
            self._pen.setWidth(PENCIL_WIDTH)
        self._pen.setColor(color)

    def set_zoom(self, factor: float):
        """Set the zoom level of the canvas (called by the slider)."""
        center = self.mapToScene(self.viewport().rect().center())
        self._zoom = factor
        t = QTransform()
        t.scale(factor, factor)
        self.setTransform(t)
        self.centerOn(center)

    def zoom_lens_radius(self) -> int:
        selected = self._selected_zoom_lens_items()
        if len(selected) == 1:
            return int(selected[0].radius_px())
        return int(self._zoom_lens_radius_px)

    def set_zoom_lens_radius(self, radius_px: int) -> None:
        clamped = max(60, min(260, int(radius_px)))
        selected = self._selected_zoom_lens_items()
        changed = False
        if clamped != self._zoom_lens_radius_px:
            self._zoom_lens_radius_px = clamped
            changed = True
        for lens in selected:
            if lens.set_radius_px(clamped):
                changed = True
        if not changed:
            return
        if self._tool == "zoom_lens" or selected:
            self.viewport().update()

    def zoom_lens_factor(self) -> float:
        selected = self._selected_zoom_lens_items()
        if len(selected) == 1:
            return float(selected[0].zoom_factor())
        return float(self._zoom_lens_factor)

    def set_zoom_lens_factor(self, factor: float) -> None:
        clamped = max(1.2, min(8.0, float(factor)))
        selected = self._selected_zoom_lens_items()
        changed = False
        if abs(clamped - self._zoom_lens_factor) >= 1e-6:
            self._zoom_lens_factor = clamped
            changed = True
        for lens in selected:
            if lens.set_zoom_factor(clamped):
                changed = True
        if not changed:
            return
        if self._tool == "zoom_lens" or selected:
            self.viewport().update()

    # ---- corner-handle resize ----
    def _find_corner_handle(self, viewport_pos: QPoint):
        """Return (item, corner_key, anchor_scene_pos) or None.

        corner_key is one of 'tl', 'tr', 'bl', 'br'.
        anchor_scene_pos is the *opposite* corner that stays fixed.
        """
        if self._tool != "select":
            return None
        hit_r = 10  # hit radius in viewport pixels
        zoom = abs(self.transform().m11()) or 1.0
        padding = 3.0 / zoom

        for item in self.scene.selectedItems():
            if not item.isVisible():
                continue
            if isinstance(item, EditableTextItem) and item._is_editing:
                continue
            sr = item.sceneBoundingRect().adjusted(-padding, -padding, padding, padding)
            corners = {
                'tl': (sr.topLeft(),     sr.bottomRight()),
                'tr': (sr.topRight(),    sr.bottomLeft()),
                'bl': (sr.bottomLeft(),  sr.topRight()),
                'br': (sr.bottomRight(), sr.topLeft()),
            }
            for key, (corner, anchor) in corners.items():
                cvp = self.mapFromScene(corner)
                if (abs(viewport_pos.x() - cvp.x()) <= hit_r and
                        abs(viewport_pos.y() - cvp.y()) <= hit_r):
                    return item, key, anchor
        return None

    def _find_rotation_handle(self, viewport_pos: QPoint):
        """Return item if viewport_pos is near its rotation handle, else None."""
        if self._tool != "select":
            return None
        hit_r = 10
        zoom = abs(self.transform().m11()) or 1.0
        padding = 3.0 / zoom
        rot_offset_vp = 28  # viewport pixels — must match drawForeground

        for item in self.scene.selectedItems():
            if not item.isVisible():
                continue
            if isinstance(item, EditableTextItem) and item._is_editing:
                continue
            sr = item.sceneBoundingRect().adjusted(-padding, -padding, padding, padding)
            top_center_scene = QPointF(sr.center().x(), sr.top())
            top_center_vp = self.mapFromScene(top_center_scene)
            handle_vp = QPoint(top_center_vp.x(), top_center_vp.y() - rot_offset_vp)
            if (abs(viewport_pos.x() - handle_vp.x()) <= hit_r and
                    abs(viewport_pos.y() - handle_vp.y()) <= hit_r):
                return item
        return None

    def _expanded_item_set(self, items) -> set[QGraphicsItem]:
        allowed_items: set[QGraphicsItem] = set()
        for item in items:
            if item in allowed_items:
                continue
            allowed_items.add(item)
            parent = item.parentItem()
            while parent is not None:
                if parent in allowed_items:
                    break
                allowed_items.add(parent)
                parent = parent.parentItem()
            stack = list(item.childItems())
            while stack:
                child = stack.pop()
                if child in allowed_items:
                    continue
                allowed_items.add(child)
                stack.extend(child.childItems())
        return allowed_items

    def _resolve_export_rect(self, selected_only: bool = False) -> tuple[QRectF, Optional[list[QGraphicsItem]]]:
        if selected_only:
            selected = [it for it in self.scene.selectedItems()]
            if selected:
                rect = selected[0].sceneBoundingRect()
                for it in selected[1:]:
                    rect = rect.united(it.sceneBoundingRect())
                return rect, selected
        return self.scene.itemsBoundingRect(), None

    def _gif_source_path(self, item: QGraphicsItem) -> Optional[Path]:
        getter = getattr(item, "source_path", None)
        if callable(getter):
            try:
                source = getter()
                if source:
                    return Path(source)
            except Exception:
                pass
        raw_path = item.data(2)
        if raw_path:
            try:
                return Path(str(raw_path))
            except Exception:
                return None
        return None

    def _load_gif_durations_ms(self, path: Path) -> list[int]:
        durations: list[int] = []
        try:
            with Image.open(path) as gif:
                global_duration = gif.info.get("duration", 100)
                for frame in ImageSequence.Iterator(gif):
                    raw = frame.info.get("duration", global_duration)
                    try:
                        value = int(raw)
                    except Exception:
                        value = 100
                    if value <= 0:
                        value = 100
                    durations.append(max(20, value))
        except Exception:
            pass
        if not durations:
            durations = [100]
        return durations

    def _relevant_gif_sources(self, only_items=None) -> list[dict]:
        allowed = self._expanded_item_set(only_items) if only_items is not None else None
        sources: list[dict] = []
        for item in self.scene.items():
            if str(item.data(1)).lower() != "gif":
                continue
            if allowed is not None and item not in allowed:
                continue
            if not item.isVisible():
                continue
            movie = getattr(item, "_movie", None)
            if movie is None:
                continue
            source_path = self._gif_source_path(item)
            if source_path is not None and source_path.is_file():
                durations = self._load_gif_durations_ms(source_path)
            else:
                durations = [100]
            cumulative: list[int] = []
            total = 0
            for delay in durations:
                total += int(delay)
                cumulative.append(total)
            if not cumulative:
                cumulative = [100]
                total = 100
            sources.append(
                {
                    "item": item,
                    "movie": movie,
                    "durations_ms": durations,
                    "cumulative_ms": cumulative,
                    "cycle_ms": max(1, total),
                }
            )
        return sources

    def _frame_index_for_time(self, source: dict, time_ms: int) -> int:
        cumulative = source["cumulative_ms"]
        if len(cumulative) <= 1:
            return 0
        cycle_ms = max(1, int(source["cycle_ms"]))
        t_mod = int(time_ms) % cycle_ms
        for idx, edge in enumerate(cumulative):
            if t_mod < edge:
                return idx
        return len(cumulative) - 1

    def _build_animation_schedule(
        self,
        sources: list[dict],
        item_animations: list[dict],
        max_frames: int = 180,
    ) -> tuple[list[int], list[int]]:
        if not sources and not item_animations:
            return [0], [100]

        cycle_candidates = [100]
        cycle_candidates.extend(int(src.get("cycle_ms", 100)) for src in sources)
        cycle_candidates.extend(int(anim.get("cycle_ms", 100)) for anim in item_animations)
        output_ms = max(cycle_candidates)
        output_ms = max(100, output_ms)
        boundaries = {0, output_ms}
        for src in sources:
            durations = [int(v) for v in src["durations_ms"]]
            if not durations:
                continue
            elapsed = 0
            while elapsed < output_ms:
                for delay in durations:
                    elapsed += max(20, delay)
                    if elapsed >= output_ms:
                        boundaries.add(output_ms)
                        break
                    boundaries.add(elapsed)
                if elapsed >= output_ms:
                    break

        for anim in item_animations:
            cycle = max(1, int(anim.get("cycle_ms", 100)))
            step = max(40, min(100, cycle // 16))
            elapsed = step
            while elapsed < output_ms:
                boundaries.add(elapsed)
                elapsed += step

        marks = sorted(boundaries)
        if len(marks) < 2:
            marks = [0, output_ms]
        if len(marks) - 1 > max_frames:
            step = float(output_ms) / float(max_frames)
            sampled = {0, output_ms}
            for i in range(1, max_frames):
                sampled.add(int(round(i * step)))
            marks = sorted(sampled)

        start_times: list[int] = []
        durations: list[int] = []
        for left, right in zip(marks[:-1], marks[1:]):
            if right <= left:
                continue
            start_times.append(left)
            durations.append(max(20, right - left))
        if not start_times:
            start_times = [0]
            durations = [100]
        return start_times, durations

    def save_animated_gif(self, target_path: Path | str, selected_only: bool = False) -> bool:
        target = Path(target_path).with_suffix(".gif")
        rect, only_items = self._resolve_export_rect(selected_only=selected_only)
        sources = self._relevant_gif_sources(only_items)
        item_animations = self._relevant_item_animations(only_items)
        if not sources and not item_animations:
            return False

        selected = [it for it in self.scene.selectedItems()]
        focus_item = self.scene.focusItem()
        for it in selected:
            it.setSelected(False)

        movie_states = []
        frames: list[Image.Image] = []
        try:
            self._suspend_live_item_animation = True
            self._stop_live_item_animation()
            for source in sources:
                movie = source["movie"]
                state = movie.state()
                frame_no = movie.currentFrameNumber()
                movie_states.append((movie, state, frame_no))
                try:
                    movie.setPaused(True)
                except Exception:
                    pass

            start_times, frame_delays = self._build_animation_schedule(sources, item_animations)
            for time_ms in start_times:
                for source in sources:
                    movie = source["movie"]
                    frame_idx = self._frame_index_for_time(source, time_ms)
                    try:
                        movie.jumpToFrame(frame_idx)
                    except Exception:
                        pass
                if item_animations:
                    self._apply_item_animations_at(item_animations, time_ms)
                qimg, _, _ = self._render_rect_to_qimage(rect, only_items)
                frame = qimage_to_pil(qimg)
                if frame.mode != "RGBA":
                    frame = frame.convert("RGBA")
                frames.append(frame)

            if not frames:
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            frames[0].save(
                target,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=frame_delays,
                loop=0,
                disposal=2,
            )
            return True
        except Exception:
            return False
        finally:
            for movie, state, frame_no in movie_states:
                try:
                    if frame_no >= 0:
                        movie.jumpToFrame(frame_no)
                except Exception:
                    pass
                try:
                    if state == QMovie.Running:
                        movie.setPaused(False)
                    elif state == QMovie.Paused:
                        movie.setPaused(True)
                    else:
                        movie.stop()
                except Exception:
                    pass
            self._restore_item_animations(item_animations)
            self._suspend_live_item_animation = False
            self._refresh_live_item_animation_state()
            for it in selected:
                it.setSelected(True)
            if focus_item:
                focus_item.setFocus()

    def _render_rect_to_qimage(self, rect: QRectF, only_items=None):
        dpr = getattr(self.window().windowHandle(), "devicePixelRatio", lambda: 1.0)()
        try:
            dpr = float(dpr)
        except Exception:
            dpr = 1.0
        w = max(1, int(math.ceil(rect.width() * dpr)))
        h = max(1, int(math.ceil(rect.height() * dpr)))
        img = QImage(w, h, QImage.Format_RGBA8888)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        hidden = []
        if only_items is not None:
            allowed_items = self._expanded_item_set(only_items)
            for it in self.scene.items():
                if it not in allowed_items:
                    hidden.append((it, it.isVisible()))
                    it.setVisible(False)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.scale(dpr, dpr)
        self.scene.render(p, QRectF(0, 0, rect.width(), rect.height()), rect)
        p.end()
        self._apply_zoom_lenses_to_image(img, rect, dpr, only_items=only_items)
        for it, vis in hidden:
            it.setVisible(vis)
        return img, rect, dpr

    def export_image(self) -> QImage:
        selected = [it for it in self.scene.selectedItems()]
        focus_item = self.scene.focusItem()
        for it in selected:
            it.setSelected(False)

        rect = self.scene.itemsBoundingRect()
        img, _, _ = self._render_rect_to_qimage(rect)

        for it in selected:
            it.setSelected(True)
        if focus_item:
            focus_item.setFocus()
        return qimage_to_pil(img)

    def export_selection(self) -> QImage:
        selected = [it for it in self.scene.selectedItems()]
        if not selected:
            return self.export_image()
        rect = selected[0].sceneBoundingRect()
        for it in selected[1:]:
            rect = rect.united(it.sceneBoundingRect())
        focus_item = self.scene.focusItem()
        for it in selected:
            it.setSelected(False)
        img, _, _ = self._render_rect_to_qimage(rect, selected)
        for it in selected:
            it.setSelected(True)
        if focus_item:
            focus_item.setFocus()
        return qimage_to_pil(img)

    def export_selection_with_geometry(self) -> Tuple[Image.Image, QRectF, Tuple[int, int], float]:
        selected = [it for it in self.scene.selectedItems()]
        if not selected:
            rect = self.scene.itemsBoundingRect()
            img, rect, dpr = self._render_rect_to_qimage(rect)
        else:
            rect = selected[0].sceneBoundingRect()
            for it in selected[1:]:
                rect = rect.united(it.sceneBoundingRect())
            focus_item = self.scene.focusItem()
            for it in selected:
                it.setSelected(False)
            img, rect, dpr = self._render_rect_to_qimage(rect, selected)
            for it in selected:
                it.setSelected(True)
            if focus_item:
                focus_item.setFocus()
        return qimage_to_pil(img), rect, (img.width(), img.height()), dpr

    def current_ocr_capture(self) -> OcrCapture:
        image, rect, pixel_size, _ = self.export_selection_with_geometry()
        anchor = self.pixmap_item if self.pixmap_item and self.pixmap_item.scene() == self.scene else None
        return OcrCapture(image=image, scene_rect=rect, pixel_size=pixel_size, anchor_item=anchor)

    def selected_ocr_text(self) -> str:
        if self.ocr_overlay and self.ocr_overlay.has_selection():
            return self.ocr_overlay.selected_text()
        if self.ocr_overlay and self.ocr_overlay.has_words():
            return self.ocr_overlay.full_text()
        return ""

    # ---- OCR scanner animation ----
    def show_ocr_scanner(self, target_rect: Optional[QRectF] = None, *, laser_color: Optional[QColor] = None) -> None:
        self.hide_ocr_scanner()
        if target_rect is None:
            target_rect = self.pixmap_item.sceneBoundingRect() if self.pixmap_item else self.scene.itemsBoundingRect()
        if target_rect is None or target_rect.isNull():
            return

        color = QColor(laser_color or ModernColors.PRIMARY)
        bar_height = 34.0
        gradient = self._build_scanner_gradient(color, bar_height)

        dim_rect = QGraphicsRectItem(target_rect)
        dim_rect.setBrush(QColor(0, 0, 0, 70))
        dim_rect.setPen(Qt.NoPen)
        dim_rect.setZValue(9997)
        dim_rect.setData(0, "ocr_scanner")
        self.scene.addItem(dim_rect)
        self._ocr_scan_dim = dim_rect

        bar_path = QGraphicsPathItem()
        bar_path.setBrush(QBrush(gradient))
        bar_path.setPen(Qt.NoPen)
        bar_path.setZValue(9999)
        bar_path.setData(0, "ocr_scanner")

        path = QPainterPath()
        path.addRect(0, 0, target_rect.width(), bar_height)
        bar_path.setPath(path)
        bar_path.setPos(target_rect.left(), target_rect.top() - bar_height)

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(22)
        glow.setColor(self._laser_tip_color(color))
        glow.setOffset(0, 0)
        bar_path.setGraphicsEffect(glow)

        self.scene.addItem(bar_path)
        self._ocr_scan_bar = bar_path

        anim = QVariantAnimation(self)
        anim.setStartValue(target_rect.top() - bar_height)
        anim.setEndValue(target_rect.bottom())
        anim.setDuration(1800)
        anim.setEasingCurve(QEasingCurve.InOutQuad)

        anim.valueChanged.connect(lambda value: bar_path.setY(float(value)))

        def _restart_scan_animation() -> None:
            if self._ocr_scan_anim is not anim:
                return
            next_direction = (
                QAbstractAnimation.Backward
                if anim.direction() == QAbstractAnimation.Forward
                else QAbstractAnimation.Forward
            )
            anim.setDirection(next_direction)
            anim.start()

        anim.finished.connect(_restart_scan_animation)
        anim.start()
        self._ocr_scan_anim = anim

    def hide_ocr_scanner(self, *, final_color: Optional[QColor] = None) -> None:
        if self._ocr_scan_anim:
            self._ocr_scan_anim.stop()
            self._ocr_scan_anim = None

        if self._ocr_scan_bar is None and self._ocr_scan_dim is None:
            return

        if self._ocr_scan_bar and final_color:
            bar_height = self._ocr_scan_bar.path().boundingRect().height()
            self._ocr_scan_bar.setBrush(QBrush(self._build_scanner_gradient(final_color, bar_height)))
        fade = QVariantAnimation(self)
        fade.setDuration(240)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.valueChanged.connect(self._set_scanner_opacity)
        fade.finished.connect(self._remove_scanner_items)
        fade.start()
        self._ocr_scan_fade = fade

    def _set_scanner_opacity(self, opacity: float) -> None:
        if self._ocr_scan_bar:
            self._ocr_scan_bar.setOpacity(float(opacity))
        if self._ocr_scan_dim:
            self._ocr_scan_dim.setOpacity(float(opacity))

    def _remove_scanner_items(self) -> None:
        if self._ocr_scan_bar:
            self.scene.removeItem(self._ocr_scan_bar)
        if self._ocr_scan_dim:
            self.scene.removeItem(self._ocr_scan_dim)
        self._ocr_scan_bar = None
        self._ocr_scan_dim = None
        self._ocr_scan_fade = None

    def _laser_tip_color(self, color: QColor) -> QColor:
        tip = QColor(color)
        tip.setAlpha(230)
        return tip

    def _build_scanner_gradient(self, color: QColor, bar_height: float) -> QLinearGradient:
        gradient = QLinearGradient(0, 0, 0, bar_height)
        top = QColor(color)
        top.setAlpha(0)
        middle = QColor(color)
        middle.setAlpha(120)
        bottom = QColor(color)
        bottom.setAlpha(255)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(0.5, middle)
        gradient.setColorAt(1.0, bottom)
        return gradient

    def undo(self):
        self.undo_stack.undo()

    def redo(self):
        self.undo_stack.redo()

    def wheelEvent(self, event):
        if self._tool == "erase" and hasattr(self.active_tool, 'wheel_event'):
            pos = self.mapToScene(event.position().toPoint())
            self.active_tool.wheel_event(event.angleDelta().y(), pos)
            event.accept()
            return

        if event.modifiers() & Qt.ControlModifier:
            selected = self.scene.selectedItems()
            if selected:
                factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
                before = {it: it.scale() for it in selected}
                for it in selected:
                    it.setScale(it.scale() * factor)
                after = {it: it.scale() for it in selected}
                if any(before[it] != after[it] for it in selected):
                    self.undo_stack.push(
                        ScaleCommand({it: (before[it], after[it]) for it in selected})
                    )
                event.accept()
                return

        # Plain scroll wheel = zoom (same as the zoom slider, but anchored to mouse)
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        step = 1.12 if delta > 0 else 1 / 1.12
        new_zoom = max(0.1, min(4.0, self._zoom * step))

        # Remember scene position under the mouse cursor before zoom
        mouse_vp = event.position().toPoint()
        scene_under_mouse = self.mapToScene(mouse_vp)

        # Apply new zoom transform (AnchorViewCenter keeps old viewport centre stable)
        self._zoom = new_zoom
        t = QTransform()
        t.scale(new_zoom, new_zoom)
        self.setTransform(t)

        # Re-anchor: place scene_under_mouse exactly at the mouse viewport pixel
        vp_center = QPointF(self.viewport().rect().center())
        offset_scene = (QPointF(mouse_vp) - vp_center) / new_zoom
        self.centerOn(scene_under_mouse - offset_scene)

        self.zoomChanged.emit(new_zoom)
        event.accept()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            key = event.key()
            if key == Qt.Key_Z:
                if self.undo_stack.canUndo():
                    self.undo_stack.undo()
                event.accept()
                return
            if key == Qt.Key_X:
                if self.undo_stack.canRedo():
                    self.undo_stack.redo()
                event.accept()
                return
            if key == Qt.Key_A:
                focus_item = self.scene.focusItem()
                if (
                    isinstance(focus_item, QGraphicsTextItem)
                    and focus_item.textInteractionFlags() != Qt.NoTextInteraction
                ):
                    super().keyPressEvent(event)
                    return
                if self._tool != "select":
                    self.set_tool("select")
                self.select_all_items()
                event.accept()
                return
        if self._tool == "erase" and hasattr(self.active_tool, 'key_press'):
            self.active_tool.key_press(event.key())
            event.accept()
            return
        if self._tool == "zoom_lens" and event.key() == Qt.Key_Escape:
            self._zoom_lens_cursor_vp = None
            self.viewport().update()
            event.accept()
            return
        super().keyPressEvent(event)

    def select_all_items(self) -> None:
        selectable = []
        for item in self.scene.items():
            if not item.isVisible():
                continue
            if item.flags() & QGraphicsItem.ItemIsSelectable:
                selectable.append(item)
        if not selectable:
            return
        self.scene.clearSelection()
        for item in selectable:
            item.setSelected(True)

    def mousePressEvent(self, event):
        if self._tool == "zoom_lens":
            vp = event.position().toPoint()
            self._zoom_lens_cursor_vp = vp
            scene_pos = self.mapToScene(vp)
            if event.button() == Qt.RightButton:
                lens = self._zoom_lens_item_at(scene_pos)
                self._show_zoom_lens_context_menu(self.viewport().mapToGlobal(vp), lens=lens)
                self.viewport().update()
                event.accept()
                return
            if event.button() == Qt.LeftButton:
                self.add_zoom_lens_item(scene_pos)
                self.viewport().update()
                event.accept()
                return
            self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._tool == "ocr":
            pos = self.mapToScene(event.position().toPoint())
            if self.ocr_overlay:
                self.ocr_overlay.start_selection(pos)
            event.accept()
            return
        if event.button() == Qt.RightButton and self._tool == "erase":
            if self.active_tool and hasattr(self.active_tool, "show_size_popup"):
                global_pos = self.viewport().mapToGlobal(event.position().toPoint())
                self.active_tool.show_size_popup(global_pos)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            if self._tool == "select":
                # Rotation handle takes priority over resize and move
                rot_item = self._find_rotation_handle(event.position().toPoint())
                if rot_item:
                    local_center = rot_item.boundingRect().center()
                    rot_item.setTransformOriginPoint(local_center)
                    center_scene = rot_item.mapToScene(local_center)
                    mouse_scene = self.mapToScene(event.position().toPoint())
                    start_angle = math.degrees(math.atan2(
                        mouse_scene.y() - center_scene.y(),
                        mouse_scene.x() - center_scene.x(),
                    ))
                    self._rotation_drag = {
                        'item': rot_item,
                        'center_scene': center_scene,
                        'start_angle': start_angle,
                        'start_rotation': rot_item.rotation(),
                        'origin': QPointF(local_center),
                    }
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return

                # Corner-handle resize takes priority over item move
                handle = self._find_corner_handle(event.position().toPoint())
                if handle:
                    item, key, anchor_scene = handle
                    start_scale = item.scale() or 1.0
                    start_pos = QPointF(item.pos())
                    start_mouse = self.mapToScene(event.position().toPoint())
                    diff = start_mouse - anchor_scene
                    start_dist = math.sqrt(diff.x() ** 2 + diff.y() ** 2)
                    if start_dist > 1e-3:
                        anchor_in_item = (anchor_scene - start_pos) / start_scale
                        self._corner_resize = {
                            'item': item,
                            'anchor_scene': anchor_scene,
                            'anchor_in_item': anchor_in_item,
                            'start_scale': start_scale,
                            'start_pos': start_pos,
                            'start_dist': start_dist,
                        }
                        event.accept()
                        return
                items = self.scene.selectedItems()
                if items:
                    self._move_snapshot = {it: it.pos() for it in items}
                self._drag_start_pos = event.position().toPoint()
            elif self._tool not in ("none", "select"):
                pos = self.mapToScene(event.position().toPoint())
                if self._tool == "text" and self._text_manager:
                    current = getattr(self._text_manager, "_current_text_item", None)
                    if current:
                        # If click inside current text item, allow editing; otherwise finish editing
                        if current.contains(current.mapFromScene(pos)):
                            super().mousePressEvent(event)
                        else:
                            self._text_manager.finish_current_editing()
                            self.set_tool("select")
                            event.accept()
                        return
                    else:
                        # Create new text item
                        item = self._text_manager.create_text_item(pos)
                        if item:
                            self.undo_stack.push(AddCommand(self.scene, item))
                        event.accept()
                        return
                if self.active_tool:
                    self.active_tool.press(pos)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._tool == "zoom_lens":
            vp = event.position().toPoint()
            self._zoom_lens_cursor_vp = vp
            self.viewport().setCursor(Qt.CrossCursor)
            self.viewport().update()
            event.accept()
            return
        # Rotation drag
        if self._rotation_drag and (event.buttons() & Qt.LeftButton):
            rd = self._rotation_drag
            mouse_scene = self.mapToScene(event.position().toPoint())
            cur_angle = math.degrees(math.atan2(
                mouse_scene.y() - rd['center_scene'].y(),
                mouse_scene.x() - rd['center_scene'].x(),
            ))
            delta = cur_angle - rd['start_angle']
            rd['item'].setRotation(rd['start_rotation'] + delta)
            self.scene.invalidate(QRectF(), QGraphicsScene.ForegroundLayer)
            event.accept()
            return

        # Corner resize drag
        if self._corner_resize and (event.buttons() & Qt.LeftButton):
            cr = self._corner_resize
            mouse_scene = self.mapToScene(event.position().toPoint())
            diff = mouse_scene - cr['anchor_scene']
            dist = math.sqrt(diff.x() ** 2 + diff.y() ** 2)
            if dist > 1e-3:
                factor = dist / cr['start_dist']
                new_scale = max(0.05, min(20.0, cr['start_scale'] * factor))
                item = cr['item']
                item.setScale(new_scale)
                new_pos = cr['anchor_scene'] - cr['anchor_in_item'] * new_scale
                item.setPos(new_pos)
                self.scene.invalidate(QRectF(), QGraphicsScene.ForegroundLayer)
            event.accept()
            return

        # Cursor hint for rotation / corner handles (no button held, select mode)
        if not event.buttons() and self._tool == "select":
            vp = event.position().toPoint()
            if self._find_rotation_handle(vp):
                self.viewport().setCursor(Qt.OpenHandCursor)
            elif self._find_corner_handle(vp):
                self.viewport().setCursor(Qt.SizeFDiagCursor)
            else:
                self.viewport().setCursor(self._select_cursor)

        if (event.buttons() & Qt.LeftButton) and self._tool == "ocr":
            pos = self.mapToScene(event.position().toPoint())
            if self.ocr_overlay:
                self.ocr_overlay.update_drag(pos)
            event.accept()
            return
        if (event.buttons() & Qt.LeftButton) and self._tool == "select":
            if self._should_start_external_drag(event):
                self._start_external_drag()
                event.accept()
                return
        if (event.buttons() & Qt.LeftButton) and self._tool not in ("none", "select", "text"):
            pos = self.mapToScene(event.position().toPoint())
            if self.active_tool:
                self.active_tool.move(pos)
            event.accept()
            return

        block_autoscroll = (event.buttons() & Qt.LeftButton) and self._tool in ("none", "select", "text")
        if block_autoscroll:
            h_value = self.horizontalScrollBar().value()
            v_value = self.verticalScrollBar().value()
            super().mouseMoveEvent(event)
            if self._tool == "select" and self.scene.selectedItems():
                self.scene.invalidate(QRectF(), QGraphicsScene.ForegroundLayer)
                self.viewport().update()
            if self.horizontalScrollBar().value() != h_value:
                self.horizontalScrollBar().setValue(h_value)
            if self.verticalScrollBar().value() != v_value:
                self.verticalScrollBar().setValue(v_value)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._tool == "zoom_lens":
            self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            # Finish rotation drag
            if self._rotation_drag:
                rd = self._rotation_drag
                self._rotation_drag = None
                self.viewport().setCursor(self._select_cursor)
                old_r = rd['start_rotation']
                new_r = rd['item'].rotation()
                if abs(old_r - new_r) > 1e-4:
                    self.undo_stack.push(RotateCommand(rd['item'], rd['origin'], old_r, new_r))
                event.accept()
                return

            # Finish corner resize
            if self._corner_resize:
                cr = self._corner_resize
                self._corner_resize = None
                item = cr['item']
                old_s, new_s = cr['start_scale'], item.scale()
                old_p, new_p = cr['start_pos'], item.pos()
                if abs(old_s - new_s) > 1e-4:
                    self.undo_stack.push(ResizeCommand(item, old_s, new_s, old_p, new_p))
                event.accept()
                return
            if self._tool == "ocr":
                event.accept()
                return
            if self._tool == "select" and self._move_snapshot:
                moved = {}
                for it, old in self._move_snapshot.items():
                    if it.pos() != old:
                        moved[it] = (old, it.pos())
                if moved:
                    self.undo_stack.push(MoveCommand(moved))
                self._move_snapshot = {}
            self._drag_start_pos = None
            if self._tool not in ("none", "select", "text"):
                pos = self.mapToScene(event.position().toPoint())
                if self.active_tool:
                    self.active_tool.release(pos)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._tool == "zoom_lens":
            self._zoom_lens_cursor_vp = None
            self.viewport().update()
        super().leaveEvent(event)

    def bring_to_front(self, item: QGraphicsItem, *, record: bool = True):
        items = self.scene.items()
        changes = {}
        if item.data(0) != "blur":
            non_blur_items = [it for it in items if it.data(0) != "blur"]
            max_z = max((it.zValue() for it in non_blur_items), default=0)
            old = item.zValue()
            new = max_z + 1
            item.setZValue(new)
            changes[item] = (old, new)
        self._ensure_blur_top(items, changes)
        self._ensure_text_top(items, changes)
        if record and changes:
            self.undo_stack.push(ZValueCommand(changes))

    def send_to_back(self, item: QGraphicsItem):
        items = self.scene.items()
        changes = {}
        if item.data(0) != "blur":
            non_blur_items = [it for it in items if it.data(0) != "blur"]
            min_z = min((it.zValue() for it in non_blur_items), default=0)
            old = item.zValue()
            new = min_z - 1
            item.setZValue(new)
            changes[item] = (old, new)
        self._ensure_blur_top(items, changes)
        self._ensure_text_top(items, changes)
        if changes:
            self.undo_stack.push(ZValueCommand(changes))

    def _ensure_blur_top(self, items, changes):
        non_blur_z = [it.zValue() for it in items if it.data(0) != "blur"]
        max_z = max(non_blur_z, default=0)
        blur_z = max_z + 1
        for it in items:
            if it.data(0) == "blur" and it.zValue() != blur_z:
                changes[it] = (it.zValue(), blur_z)
                it.setZValue(blur_z)

    def _ensure_text_top(self, items, changes):
        text_items = [it for it in items if it.data(0) == "text" or isinstance(it, QGraphicsTextItem)]
        if not text_items:
            return
        base_max = max((it.zValue() for it in items if it not in text_items), default=0)
        next_z = base_max + 1
        for it in text_items:
            if it.zValue() < next_z:
                changes[it] = (it.zValue(), next_z)
                it.setZValue(next_z)
            next_z = max(next_z, it.zValue()) + 1

    def _context_targets(self, clicked_item: QGraphicsItem) -> list[QGraphicsItem]:
        selected = list(self.scene.selectedItems())
        if clicked_item in selected and selected:
            return selected
        return [clicked_item]

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        items = self.scene.items(scene_pos)
        if items:
            item = items[0]
            while item.parentItem() is not None and not bool(item.flags() & QGraphicsItem.ItemIsSelectable):
                item = item.parentItem()
            targets = self._context_targets(item)
            menu = QMenu(self)
            act_add_meme = None
            if isinstance(item, QGraphicsPixmapItem) and item.data(0) in {"screenshot", "meme"}:
                act_add_meme = menu.addAction("Добавить в мемы")
                menu.addSeparator()
            act_front = menu.addAction("На передний план")
            act_back = menu.addAction("На задний план")
            anim_targets = [it for it in targets if self._can_animate_item(it)]
            anim_actions: dict = {}
            pulse_targets = [it for it in anim_targets if self._is_pulse_eligible(it)]
            if anim_targets:
                anim_menu = menu.addMenu("Animation")
                act_anim_none = anim_menu.addAction("Без анимации")
                act_anim_draw = anim_menu.addAction("Draw animation")
                act_anim_pulse = anim_menu.addAction("Pulse")
                act_anim_pulse.setEnabled(bool(pulse_targets))
                for anim_action in (act_anim_none, act_anim_draw, act_anim_pulse):
                    anim_action.setCheckable(True)
                kinds = {self._item_animation_kind(it) for it in anim_targets}
                current_kind = kinds.pop() if len(kinds) == 1 else ""
                act_anim_none.setChecked(current_kind == ANIMATION_NONE)
                act_anim_draw.setChecked(current_kind == ANIMATION_DRAW)
                act_anim_pulse.setChecked(current_kind == ANIMATION_PULSE and bool(pulse_targets))
                anim_actions = {
                    act_anim_none: ANIMATION_NONE,
                    act_anim_draw: ANIMATION_DRAW,
                    act_anim_pulse: ANIMATION_PULSE,
                }
            act_del = menu.addAction("Удалить")
            chosen = menu.exec(event.globalPos())
            if chosen == act_add_meme and act_add_meme is not None:
                qimg = item.pixmap().toImage()
                if not qimg.isNull():
                    try:
                        path = save_meme_image(qimage_to_pil(qimg))
                    except Exception as exc:
                        QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить мем: {exc}")
                    else:
                        win = self.window()
                        if hasattr(win, "notify_meme_saved"):
                            win.notify_meme_saved(path)
                event.accept()
                return
            if chosen == act_front:
                self.bring_to_front(item)
            elif chosen == act_back:
                self.send_to_back(item)
            elif chosen in anim_actions and anim_targets:
                target_kind = anim_actions[chosen]
                changed = False
                if target_kind == ANIMATION_PULSE:
                    for target in pulse_targets:
                        if self._set_item_animation_kind(target, ANIMATION_PULSE):
                            changed = True
                    for target in anim_targets:
                        if target in pulse_targets:
                            continue
                        if self._set_item_animation_kind(target, ANIMATION_NONE):
                            changed = True
                else:
                    for target in anim_targets:
                        if self._set_item_animation_kind(target, target_kind):
                            changed = True
                if changed:
                    self._refresh_live_item_animation_state()
                    self.viewport().update()
            elif chosen == act_del:
                for it in targets:
                    self.scene.removeItem(it)
                    self.handle_item_removed(it)
                    self.undo_stack.push(
                        RemoveCommand(
                            self.scene,
                            it,
                            on_removed=self.handle_item_removed,
                            on_restored=self.handle_item_restored,
                        )
                    )
            event.accept()
            return
        super().contextMenuEvent(event)
