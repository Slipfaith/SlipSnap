from typing import Optional, List
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QImage, QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem

from .styles import ModernColors
from .icon_factory import create_pencil_cursor, create_select_cursor
from logic import qimage_to_pil
from editor.text_tools import TextManager
from editor.tools.selection_tool import SelectionTool
from editor.tools.pencil_tool import PencilTool
from editor.tools.shape_tools import RectangleTool, EllipseTool
from editor.tools.blur_tool import BlurTool
from editor.tools.eraser_tool import EraserTool
from editor.tools.line_arrow_tool import LineTool, ArrowTool


class Canvas(QGraphicsView):
    """Drawing canvas holding the image and drawn items."""

    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.scene.addItem(self.pixmap_item)

        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)

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
        self._pen = QPen(QColor(ModernColors.PRIMARY), 3)
        self._pen.setCapStyle(Qt.RoundCap)
        self._pen.setJoinStyle(Qt.RoundJoin)
        self._undo: List[QGraphicsItem] = []
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

        # cursors
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

    # public API
    def set_tool(self, tool: str):
        if self._text_manager:
            self._text_manager.finish_current_editing()

        self._tool = tool
        if tool == "select":
            self.viewport().setCursor(self._select_cursor)
        elif tool in {"rect", "ellipse", "line", "arrow", "blur", "erase"}:
            self.viewport().setCursor(Qt.CrossCursor)
        elif tool == "free":
            self.viewport().setCursor(self._pencil_cursor)
        elif tool == "text":
            self.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)
        self.active_tool = self.tools.get(tool)
        self._apply_lock_state()

        # auto-disable live text when drawing
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
        self._pen.setColor(color)

    def export_image(self) -> Image.Image:
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
        p.translate(-rect.left(), -rect.top())
        self.scene.render(p)
        p.end()
        return qimage_to_pil(img)

    def undo(self):
        if self._undo:
            item = self._undo.pop()
            self.scene.removeItem(item)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            selected = self.scene.selectedItems()
            if selected:
                factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
                for it in selected:
                    it.setScale(it.scale() * factor)
                event.accept()
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._tool not in ("none", "select"):
            pos = self.mapToScene(event.position().toPoint())
            if self._tool == "text":
                if self._text_manager:
                    item = self._text_manager.create_text_item(pos)
                    if item:
                        self._undo.append(item)
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
        if event.button() == Qt.LeftButton and self._tool not in ("none", "select", "text"):
            pos = self.mapToScene(event.position().toPoint())
            if self.active_tool:
                self.active_tool.release(pos)
            event.accept()
            return
        super().mouseReleaseEvent(event)
