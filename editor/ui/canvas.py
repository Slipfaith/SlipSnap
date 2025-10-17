from typing import Optional, Dict
import math

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QPixmap, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsItem,
    QMenu,
)

from .styles import ModernColors
from .icon_factory import create_pencil_cursor, create_select_cursor
from logic import qimage_to_pil
from editor.text_tools import TextManager, EditableTextItem
from editor.tools.selection_tool import SelectionTool
from editor.tools.pencil_tool import PencilTool
from editor.tools.shape_tools import RectangleTool, EllipseTool
from editor.tools.blur_tool import BlurTool
from editor.tools.eraser_tool import EraserTool
from editor.tools.line_arrow_tool import LineTool, ArrowTool
from editor.undo_commands import AddCommand, MoveCommand, ScaleCommand, ZValueCommand, RemoveCommand
from editor.image_utils import images_from_mime

MARKER_ALPHA = 80
PENCIL_WIDTH = 3
MARKER_WIDTH = 15


class Canvas(QGraphicsView):
    """Drawing canvas holding the image and drawn items."""

    imageDropped = Signal(QImage)

    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setAcceptDrops(True)

        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.pil_image = qimage_to_pil(image)  # store original PIL image
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.pixmap_item.setData(0, "screenshot")
        self.scene.addItem(self.pixmap_item)

        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.setStyleSheet(f"""
            QGraphicsView {{
                background: {ModernColors.SURFACE_VARIANT};
                border: 1px solid {ModernColors.BORDER};
                border-radius: 12px;
                padding: 2px;
            }}
            QGraphicsView:focus {{
                border: 2px solid {ModernColors.BORDER_FOCUS};
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
            if isinstance(it, QGraphicsPixmapItem):
                it.setFlag(QGraphicsItem.ItemIsMovable, enabled)
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
        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.pixmap_item.setData(0, "screenshot")
        self.scene.addItem(self.pixmap_item)
        self.pil_image = qimage_to_pil(image)
        self.undo_stack.clear()
        if self._text_manager:
            self._text_manager.finish_current_editing()
        self._apply_lock_state()

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
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

        self._apply_lock_state()

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

    def export_image(self) -> QImage:
        selected = [it for it in self.scene.selectedItems()]
        focus_item = self.scene.focusItem()
        for it in selected:
            it.setSelected(False)

        rect = self.scene.itemsBoundingRect()
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
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.scale(dpr, dpr)
        self.scene.render(p, QRectF(0, 0, rect.width(), rect.height()), rect)
        p.end()

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
        for it in self.scene.items():
            if it not in selected:
                hidden.append((it, it.isVisible()))
                it.setVisible(False)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.scale(dpr, dpr)
        self.scene.render(p, QRectF(0, 0, rect.width(), rect.height()), rect)
        p.end()
        for it, vis in hidden:
            it.setVisible(vis)
        return qimage_to_pil(img)

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
        if self._tool == "erase" and hasattr(self.active_tool, 'key_press'):
            self.active_tool.key_press(event.key())
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
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
        if (event.buttons() & Qt.LeftButton) and self._tool not in ("none", "select", "text"):
            pos = self.mapToScene(event.position().toPoint())
            if self.active_tool:
                self.active_tool.move(pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
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

    def bring_to_front(self, item: QGraphicsItem):
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
        if changes:
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

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        items = self.scene.items(scene_pos)
        if items:
            item = items[0]
            menu = QMenu(self)
            act_front = menu.addAction("На передний план")
            act_back = menu.addAction("На задний план")
            act_del = menu.addAction("Удалить")
            chosen = menu.exec(event.globalPos())
            if chosen == act_front:
                self.bring_to_front(item)
            elif chosen == act_back:
                self.send_to_back(item)
            elif chosen == act_del:
                targets = [it for it in self.scene.selectedItems() if it != self.pixmap_item]
                if item not in targets and item != self.pixmap_item:
                    targets = [item]
                for it in targets:
                    self.scene.removeItem(it)
                    self.undo_stack.push(RemoveCommand(self.scene, it))
            event.accept()
            return
        super().contextMenuEvent(event)
