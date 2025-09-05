from typing import Optional, Dict
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QPixmap, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsItem,
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
from editor.undo_commands import AddCommand, MoveCommand, ScaleCommand

MARKER_ALPHA = 80
PENCIL_WIDTH = 3
MARKER_WIDTH = 15


class Canvas(QGraphicsView):
    """Drawing canvas holding the image and drawn items."""

    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.pil_image = qimage_to_pil(image)  # store original PIL image
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
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
        self.setDragMode(QGraphicsView.NoDrag)

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

        win = self.window()
        try:
            if tool != "select" and hasattr(win, "live_manager") and win.live_manager and win.live_manager.active:
                win.live_manager.disable()
                if hasattr(win, "statusBar"):
                    win.statusBar().showMessage(
                        "🔍 Live Text — выключено (переключился на инструмент рисования)", 2200)
        except Exception:
            pass

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
