from typing import Optional, Dict, Tuple
import math

from PySide6.QtCore import (
    Qt,
    QPointF,
    QRectF,
    Signal,
    QMarginsF,
    QEasingCurve,
    QVariantAnimation,
    QAbstractAnimation,
    QTimer,
)
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QUndoStack, QLinearGradient, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsItem,
    QGraphicsTextItem,
    QMenu,
    QMessageBox,
    QFrame,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsDropShadowEffect,
)
from PIL import Image

from .styles import ModernColors
from .high_quality_pixmap_item import HighQualityPixmapItem
from .icon_factory import create_pencil_cursor, create_select_cursor
from logic import qimage_to_pil
from editor.text_tools import TextManager
from editor.ocr_overlay import OcrSelectionOverlay, OcrCapture
from editor.tools.selection_tool import SelectionTool
from editor.tools.pencil_tool import PencilTool
from editor.tools.shape_tools import RectangleTool, EllipseTool
from editor.tools.blur_tool import BlurTool
from editor.tools.eraser_tool import EraserTool
from editor.tools.line_arrow_tool import LineTool, ArrowTool
from editor.undo_commands import AddCommand, MoveCommand, ScaleCommand, ZValueCommand, RemoveCommand
from editor.image_utils import images_from_mime
from meme_library import save_meme_image

from design_tokens import Metrics

MARKER_ALPHA = Metrics.MARKER_ALPHA
PENCIL_WIDTH = Metrics.PENCIL_WIDTH
MARKER_WIDTH = Metrics.MARKER_WIDTH


class Canvas(QGraphicsView):
    """Drawing canvas holding the image and drawn items."""

    imageDropped = Signal(QImage)
    toolChanged = Signal(str)

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
        self._blur_refresh_pending = False
        self._blur_refreshing = False
        self.scene.changed.connect(self._queue_blur_refresh)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        super().drawForeground(painter, rect)
        selected = [it for it in self.scene.selectedItems() if it.isVisible()]
        if not selected:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        stroke = QColor(ModernColors.PRIMARY)
        stroke.setAlpha(220)
        fill = QColor(ModernColors.PRIMARY)
        fill.setAlpha(50)
        scale = abs(self.transform().m11()) or 1.0
        scale = max(scale, 1e-3)

        for item in selected:
            padding = 4.0 / scale
            scene_rect = item.sceneBoundingRect().adjusted(-padding, -padding, padding, padding)
            view_rect = self.mapFromScene(scene_rect).boundingRect()
            side = min(view_rect.width(), view_rect.height())
            radius = min(12.0, max(4.0, side * 0.25))
            radius_scene = radius / scale

            path = QPainterPath()
            path.addRoundedRect(scene_rect, radius_scene, radius_scene)

            painter.fillPath(path, QBrush(fill))
            pen = QPen(stroke, 2.2)
            pen.setCosmetic(True)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.restore()

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
        self.update_scene_rect()

    def handle_item_removed(self, item: QGraphicsItem) -> None:
        if item is self.pixmap_item or item.data(1) == "base":
            self.pixmap_item = None
            self.pil_image = None
        self.update_scene_rect()

    def handle_item_restored(self, item: QGraphicsItem) -> None:
        if isinstance(item, QGraphicsPixmapItem) and item.data(1) == "base":
            self.pixmap_item = item
            qimg = item.pixmap().toImage()
            if not qimg.isNull():
                self.pil_image = qimage_to_pil(qimg)
            if isinstance(item, HighQualityPixmapItem):
                item.reset_scale_tracking()
        self.update_scene_rect()

    def set_tool(self, tool: str):
        if self._text_manager:
            self._text_manager.finish_current_editing()

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
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

        if hasattr(self, "ocr_overlay"):
            self.ocr_overlay.set_active(tool == "ocr")
        self.toolChanged.emit(tool)
        self._apply_lock_state()

    # ---- scene management ----
    def update_scene_rect(self, padding: float = 48.0) -> None:
        """Update the scrollable area to fit all items with padding."""
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 0, 0)
        margins = QMarginsF(padding, padding, padding, padding)
        self.scene.setSceneRect(rect.marginsAdded(margins))

    def _queue_blur_refresh(self, _regions=None) -> None:
        if self._blur_refreshing or self._blur_refresh_pending:
            return
        self._blur_refresh_pending = True
        QTimer.singleShot(0, self._refresh_blur_items)

    def _refresh_blur_items(self) -> None:
        if self._blur_refreshing:
            return
        self._blur_refresh_pending = False
        self._blur_refreshing = True
        try:
            for item in self.scene.items():
                if item.data(0) == "blur" and hasattr(item, "refresh"):
                    item.refresh()
        finally:
            self._blur_refreshing = False

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
        """Set the zoom level of the canvas."""
        self._zoom = factor
        self.resetTransform()
        self.scale(factor, factor)

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
            for it in self.scene.items():
                if it not in only_items:
                    hidden.append((it, it.isVisible()))
                    it.setVisible(False)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.scale(dpr, dpr)
        self.scene.render(p, QRectF(0, 0, rect.width(), rect.height()), rect)
        p.end()
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
        super().wheelEvent(event)

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
        if self._tool == "erase" and hasattr(self.active_tool, 'key_press'):
            self.active_tool.key_press(event.key())
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
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
                items = self.scene.selectedItems()
                if items:
                    self._move_snapshot = {it: it.pos() for it in items}
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
        if (event.buttons() & Qt.LeftButton) and self._tool == "ocr":
            pos = self.mapToScene(event.position().toPoint())
            if self.ocr_overlay:
                self.ocr_overlay.update_drag(pos)
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
            if self.horizontalScrollBar().value() != h_value:
                self.horizontalScrollBar().setValue(h_value)
            if self.verticalScrollBar().value() != v_value:
                self.verticalScrollBar().setValue(v_value)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
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
            elif self._tool not in ("none", "select", "text"):
                pos = self.mapToScene(event.position().toPoint())
                if self.active_tool:
                    self.active_tool.release(pos)
                event.accept()
                return
        super().mouseReleaseEvent(event)

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

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        items = self.scene.items(scene_pos)
        if items:
            item = items[0]
            menu = QMenu(self)
            act_add_meme = None
            if isinstance(item, QGraphicsPixmapItem) and item.data(0) in {"screenshot", "meme"}:
                act_add_meme = menu.addAction("Добавить в мемы")
                menu.addSeparator()
            act_front = menu.addAction("На передний план")
            act_back = menu.addAction("На задний план")
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
            elif chosen == act_del:
                targets = list(self.scene.selectedItems())
                if item not in targets:
                    targets = [item]
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
