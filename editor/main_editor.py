# -*- coding: utf-8 -*-
import math
from typing import Optional, List
from pathlib import Path
from PIL import Image, ImageQt

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QImage, QKeySequence, QPixmap, QAction,
    QCursor, QTextCursor, QTextCharFormat, QIcon, QBrush, QLinearGradient
)
from PySide6.QtWidgets import (
    QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
    QFileDialog, QMessageBox, QToolBar, QLabel, QWidget, QHBoxLayout,
    QToolButton, QApplication, QGraphicsTextItem,
    QDialog, QGridLayout
)

from logic import qimage_to_pil, HISTORY_DIR, save_history
from editor.text_tools import TextManager, EditableTextItem
from editor.ocr_tools import OCRManager
from editor.live_ocr import LiveTextManager
from editor.tools.selection_tool import SelectionTool
from editor.tools.pencil_tool import PencilTool
from editor.tools.shape_tools import RectangleTool, EllipseTool
from editor.tools.blur_tool import BlurTool
from editor.tools.eraser_tool import EraserTool
from editor.tools.line_arrow_tool import LineTool, ArrowTool


# =========================
# Modern Color Scheme
# =========================
class ModernColors:
    # Primary colors
    PRIMARY = "#2563eb"  # Modern blue
    PRIMARY_HOVER = "#1d4ed8"
    PRIMARY_LIGHT = "#dbeafe"

    # Surface colors
    SURFACE = "#ffffff"
    SURFACE_VARIANT = "#f8fafc"
    SURFACE_HOVER = "#f1f5f9"

    # Border colors
    BORDER = "#e2e8f0"
    BORDER_FOCUS = "#3b82f6"

    # Text colors
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#64748b"
    TEXT_MUTED = "#94a3b8"

    # Status colors
    SUCCESS = "#10b981"
    WARNING = "#f59e0b"
    ERROR = "#ef4444"


# =========================
# Canvas (холст / сцена)
# =========================
class Canvas(QGraphicsView):
    """Холст для рисования и редактирования изображений"""

    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Основное изображение
        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.scene.addItem(self.pixmap_item)

        # Настройки UI — без автоскролла, содержимое центрировано
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)

        # Modern canvas styling
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

        # Инициализация инструментов
        self._tool = "select"
        self._pen = QPen(QColor(ModernColors.PRIMARY), 3)
        self._pen.setCapStyle(Qt.RoundCap)
        self._pen.setJoinStyle(Qt.RoundJoin)
        self._undo: List[QGraphicsItem] = []
        self._text_manager: Optional[TextManager] = None

        # Tool handlers
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

        # Курсоры
        self._create_custom_cursors()
        self._apply_lock_state()

    # ---- сервис ----
    def _create_custom_cursors(self):
        """Создает кастомные курсоры для инструментов"""
        # Курсор карандаша - более современный дизайн
        pencil_pixmap = QPixmap(24, 24)
        pencil_pixmap.fill(Qt.transparent)
        painter = QPainter(pencil_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(ModernColors.TEXT_PRIMARY), 2.5))
        painter.drawLine(4, 19, 19, 4)
        painter.setPen(QPen(QColor(ModernColors.PRIMARY), 1.5))
        painter.drawEllipse(17, 2, 5, 5)
        painter.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 1.5))
        painter.drawLine(2, 21, 5, 18)
        painter.end()
        self._pencil_cursor = QCursor(pencil_pixmap, 4, 19)

        # Современный курсор для выделения - более изящный
        select_pixmap = QPixmap(24, 24)
        select_pixmap.fill(Qt.transparent)
        painter = QPainter(select_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Основная стрелка с градиентом
        painter.setPen(QPen(QColor(ModernColors.TEXT_PRIMARY), 1.8))
        painter.setBrush(QBrush(QColor(ModernColors.TEXT_PRIMARY)))

        # Более элегантная форма стрелки
        points = [
            QPointF(3, 3), QPointF(3, 17), QPointF(8, 13),
            QPointF(12, 18), QPointF(15, 16), QPointF(10, 10), QPointF(18, 3)
        ]
        painter.drawPolygon(points)

        # Добавляем тонкую белую обводку для контраста
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(points)

        painter.end()
        self._select_cursor = QCursor(select_pixmap, 3, 3)

    def _set_pixmap_items_interactive(self, enabled: bool):
        """Включить/выключить перетаскивание и прием мыши у всех QGraphicsPixmapItem."""
        for it in self.scene.items():
            if isinstance(it, QGraphicsPixmapItem):
                it.setFlag(QGraphicsItem.ItemIsMovable, enabled)
                it.setAcceptedMouseButtons(Qt.AllButtons if enabled else Qt.NoButton)
                if not enabled and it.isSelected():
                    it.setSelected(False)

    def _apply_lock_state(self):
        """Лочим фоновые картинки при активном инструменте рисования."""
        lock = self._tool not in ("none", "select")
        self._set_pixmap_items_interactive(not lock)
        self.setDragMode(QGraphicsView.NoDrag)

    # ---- публичное API холста ----
    def set_tool(self, tool: str):
        """Установить текущий инструмент"""
        # Завершаем редактирование текста при смене инструмента
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

        # Авто-отключение Live Text при переходе к рисованию,
        # чтобы перехват мыши Live-слоем не мешал инструментам
        win = self.window()
        try:
            if tool != "select" and hasattr(win, "live_manager") and win.live_manager and win.live_manager.active:
                win.live_manager.disable()
                if hasattr(win, "statusBar"):
                    win.statusBar().showMessage("🔍 Live Text — выключено (переключился на инструмент рисования)", 2200)
        except Exception:
            pass

    def set_text_manager(self, text_manager: TextManager):
        """Установить менеджер текста"""
        self._text_manager = text_manager

    def set_pen_width(self, w: int):
        self._pen.setWidth(w)

    def set_pen_color(self, color: QColor):
        self._pen.setColor(color)

    def export_image(self) -> Image.Image:
        """Экспортировать текущую сцену в PIL.Image"""
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

    # ---- мышь / колёсико ----
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



# =========================
# UI helpers (цвет/палитра)
# =========================
class ColorButton(QToolButton):
    """Кнопка выбора цвета"""

    def __init__(self, color: QColor):
        super().__init__()
        self.color = color
        self.setFixedSize(24, 20)
        self.update_color()

    def update_color(self):
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {self.color.name()};
                border: 1px solid {ModernColors.BORDER};
                border-radius: 6px;
                min-width: 20px;
                min-height: 16px;
            }}
            QToolButton:hover {{
                border: 2px solid {ModernColors.PRIMARY};
                transform: scale(1.05);
            }}
            QToolButton:pressed {{
                transform: scale(0.95);
            }}
        """)

    def set_color(self, color: QColor):
        self.color = color
        self.update_color()


class HexColorDialog(QDialog):
    """Миниатюрная гексагональная палитра цветов"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup)
        self.selected = None
        self.setStyleSheet(f"""
            QDialog {{
                background: {ModernColors.SURFACE};
                border: 1px solid {ModernColors.BORDER};
                border-radius: 12px;
                padding: 8px;
            }}
        """)

        colors = [
            "#1e293b", "#64748b", "#dc2626",
            "#ea580c", "#eab308", "#16a34a", "#0891b2",
            "#2563eb", "#7c3aed", "#ffffff"
        ]
        positions = [
            (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 1), (2, 2), (2, 3)
        ]

        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        for pos, col in zip(positions, colors):
            btn = QToolButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f"""
                QToolButton{{
                    background: {col};
                    border: 2px solid {ModernColors.BORDER};
                    border-radius: 12px;
                }}
                QToolButton:hover{{
                    border: 2px solid {ModernColors.PRIMARY};
                    transform: scale(1.1);
                }}
                QToolButton:pressed{{
                    transform: scale(0.9);
                }}
            """)
            btn.clicked.connect(lambda _=None, c=col: self._choose(c))
            layout.addWidget(btn, *pos)

    def _choose(self, color_str):
        self.selected = QColor(color_str)
        self.accept()


# =========================
# Главное окно редактора
# =========================
class EditorWindow(QMainWindow):
    """Главное окно редактора"""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")

        # Рассчитываем минимальные размеры для видимости всех иконок
        # Левый тулбар: 7 кнопок по 52px + отступы = ~400px высота
        # Верхний тулбар: ~8 кнопок + цвет + разделители = ~500px ширина
        min_width = 580  # достаточно для всех верхних иконок
        min_height = 480  # достаточно для всех левых иконок
        self.setMinimumSize(min_width, min_height)

        # Инициализация компонентов
        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.ocr_manager = OCRManager(cfg)
        self.live_manager = LiveTextManager(self.canvas, self.ocr_manager)

        self.setCentralWidget(self.canvas)
        self._setup_styles()
        self._create_toolbar()

        # Подогнать окно под картинку ПОСЛЕ создания сцены и тулбаров
        QTimer.singleShot(0, lambda q=qimg: self._size_to_image(q))

        self.statusBar().showMessage(
            "Готово | Ctrl+N: новый скриншот | Ctrl+K: коллаж | Ctrl+Alt+O: OCR | Ctrl+L: Live | Del: удалить | Ctrl +/-: масштаб"
        )

    def _setup_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {ModernColors.SURFACE};
                color: {ModernColors.TEXT_PRIMARY};
            }}

            QToolBar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ModernColors.SURFACE},
                    stop:1 {ModernColors.SURFACE_VARIANT});
                border: none;
                border-bottom: 1px solid {ModernColors.BORDER};
                spacing: 6px;
                padding: 12px 16px;
                font-weight: 500;
                font-size: 13px;
            }}

            QToolButton {{
                background: transparent;
                border: none;
                padding: 10px 14px;
                border-radius: 10px;
                font-weight: 500;
                color: {ModernColors.TEXT_SECONDARY};
                min-width: 32px;
                min-height: 32px;
                font-size: 16px;
            }}

            QToolButton:hover {{
                background: {ModernColors.SURFACE_HOVER};
                color: {ModernColors.TEXT_PRIMARY};
                transform: translateY(-1px);
            }}

            QToolButton:pressed {{
                background: {ModernColors.PRIMARY_LIGHT};
                transform: translateY(0px);
            }}

            QToolButton:checked {{
                background: {ModernColors.PRIMARY};
                color: white;
                border: 1px solid {ModernColors.PRIMARY_HOVER};
            }}

            QToolButton:checked:hover {{
                background: {ModernColors.PRIMARY_HOVER};
            }}

            QLabel {{
                color: {ModernColors.TEXT_MUTED};
                font-size: 12px;
                font-weight: 500;
                margin: 0 6px;
            }}

            QToolBar::separator {{
                background: {ModernColors.BORDER};
                width: 1px;
                margin: 6px 12px;
            }}

            QStatusBar {{
                background: {ModernColors.SURFACE_VARIANT};
                border-top: 1px solid {ModernColors.BORDER};
                color: {ModernColors.TEXT_SECONDARY};
                font-size: 12px;
                padding: 6px 16px;
            }}
        """)

    def _size_to_image(self, qimg: QImage):
        """Подогнать размер окна под размер картинки и центрировать."""
        self.canvas.scene.setSceneRect(self.canvas.scene.itemsBoundingRect())

        # Размеры панелей
        toolbars = self.findChildren(QToolBar)
        left_w = sum(tb.sizeHint().width() for tb in toolbars if tb.orientation() == Qt.Vertical)
        top_h = sum(tb.sizeHint().height() for tb in toolbars if tb.orientation() == Qt.Horizontal)
        status_h = self.statusBar().sizeHint().height() if self.statusBar() else 0

        # Доступная область экрана
        screen = self.screen() or QApplication.primaryScreen()
        ag = screen.availableGeometry()

        # Целевые размеры: картинка 1:1 + панели + небольшой запас
        target_w = qimg.width() + left_w + 32
        target_h = qimg.height() + top_h + status_h + 32
        target_w = min(target_w, ag.width() - 40)
        target_h = min(target_h, ag.height() - 40)

        self.resize(target_w, target_h)
        self.move(ag.center().x() - self.width() // 2, ag.center().y() - self.height() // 2)

    # ---- тулбары/кнопки ----
    def _create_toolbar(self):
        # Левый тулбар с инструментами
        tools_tb = QToolBar("Tools")
        tools_tb.setOrientation(Qt.Vertical)
        tools_tb.setMovable(False)
        tools_tb.setFloatable(False)
        self.addToolBar(Qt.LeftToolBarArea, tools_tb)

        # Современные векторные иконки - увеличенные для верхнего тулбара
        def make_icon_rect():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
            p.drawRect(8, 8, 24, 24);
            p.end();
            return QIcon(pm)

        def make_icon_ellipse():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
            p.drawEllipse(8, 8, 24, 24);
            p.end();
            return QIcon(pm)

        def make_icon_line():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(10, 30, 30, 10);
            p.end();
            return QIcon(pm)

        def make_icon_arrow():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(10, 30, 28, 12)
            p.drawLine(28, 12, 23, 15);
            p.drawLine(28, 12, 25, 17);
            p.end();
            return QIcon(pm)

        def make_icon_pencil():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 3))
            p.drawLine(10, 30, 30, 10)
            p.setPen(QPen(QColor(ModernColors.PRIMARY), 2.5))
            p.drawEllipse(27, 7, 6, 6);
            p.end();
            return QIcon(pm)

        def make_icon_text():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
            f = p.font();
            f.setBold(True);
            f.setPointSize(20);
            p.setFont(f)
            p.drawText(pm.rect(), Qt.AlignCenter, "T");
            p.end();
            return QIcon(pm)

        def make_icon_blur():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            grad = QLinearGradient(10, 10, 30, 30)
            grad.setColorAt(0, QColor(ModernColors.TEXT_SECONDARY))
            grad.setColorAt(1, QColor(ModernColors.SURFACE))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRect(8, 8, 24, 24)
            p.end();
            return QIcon(pm)

        def make_icon_eraser():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
            p.setBrush(QBrush(QColor(ModernColors.TEXT_SECONDARY)))
            p.drawPolygon([
                QPointF(10, 25), QPointF(20, 15), QPointF(30, 25), QPointF(20, 35)
            ])
            p.end();
            return QIcon(pm)

        def make_icon_select():
            pm = QPixmap(40, 40);
            pm.fill(Qt.transparent)
            p = QPainter(pm);
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(ModernColors.TEXT_SECONDARY), 2.5))
            p.setBrush(QBrush(QColor(ModernColors.TEXT_SECONDARY)))
            points = [QPointF(10, 10), QPointF(10, 30), QPointF(17, 25), QPointF(25, 30), QPointF(30, 25),
                      QPointF(20, 17), QPointF(30, 10)]
            p.drawPolygon(points);
            p.end();
            return QIcon(pm)

        self._tool_buttons = []

        def add_tool(tool, icon, tooltip):
            btn = QToolButton()
            btn.setIcon(icon)
            btn.setIconSize(QSize(40, 40))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedSize(52, 52)
            btn.clicked.connect(lambda checked, t=tool: self.canvas.set_tool(t))
            tools_tb.addWidget(btn)
            self._tool_buttons.append(btn)
            return btn

        add_tool("select", make_icon_select(), "Выделение")
        add_tool("rect", make_icon_rect(), "Прямоугольник")
        add_tool("ellipse", make_icon_ellipse(), "Эллипс")
        add_tool("line", make_icon_line(), "Линия")
        add_tool("arrow", make_icon_arrow(), "Стрелка")
        add_tool("free", make_icon_pencil(), "Карандаш")
        add_tool("blur", make_icon_blur(), "Блюр")
        add_tool("erase", make_icon_eraser(), "Ластик")
        add_tool("text", make_icon_text(), "Текст")

        self._tool_buttons[0].setChecked(True)
        self.canvas.set_tool("select")

        # Верхняя панель действий
        tb = QToolBar("Actions")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        def add_action(toolbar, text, fn, checkable=False, sc=None, icon_text="", show_text=False):
            a = QAction(text, self)
            a.setCheckable(checkable)
            if sc:
                a.setShortcut(QKeySequence(sc))
            self.addAction(a)
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(fn if checkable else (lambda _checked=False: fn()))
            btn = QToolButton()
            btn.setDefaultAction(a)
            if show_text:
                btn.setText(f"{icon_text} {text}" if icon_text and text else (text or icon_text))
            else:
                btn.setText(icon_text)
                btn.setToolTip(text)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            toolbar.addWidget(btn)
            return a, btn

        self.color_btn = ColorButton(QColor(ModernColors.PRIMARY))
        self.color_btn.setToolTip("Цвет")
        self.color_btn.clicked.connect(self.choose_color)
        tb.addWidget(self.color_btn)

        tb.addSeparator()

        # NEW: Live Text + копирование выделенного текста
        self.act_live, _ = add_action(tb, "Live", self.toggle_live_text, sc="Ctrl+L", icon_text="🔍", show_text=False)
        self.act_live_copy, _ = add_action(tb, "Текст", self.copy_live_text, sc="Ctrl+Shift+C", icon_text="📄",
                                           show_text=False)

        # Остальные действия
        self.act_ocr, _ = add_action(tb, "OCR", self.ocr_current, sc="Ctrl+Alt+O", icon_text="📄", show_text=False)
        self.act_new, _ = add_action(tb, "Новый снимок", self.add_screenshot, sc="Ctrl+N", icon_text="📸",
                                     show_text=False)
        self.act_collage, _ = add_action(tb, "Коллаж", self.open_collage, sc="Ctrl+K", icon_text="🧩", show_text=False)
        add_action(tb, "Копировать", self.copy_to_clipboard, sc="Ctrl+C", icon_text="📋", show_text=False)
        add_action(tb, "Сохранить", self.save_image, sc="Ctrl+S", icon_text="💾", show_text=False)
        add_action(tb, "Отмена", lambda: self.canvas.undo(), sc="Ctrl+Z", icon_text="↶", show_text=False)

        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        # Современный стиль для тулбара инструментов
        tools_tb.setStyleSheet(f"""
            QToolBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {ModernColors.SURFACE},
                    stop:1 {ModernColors.SURFACE_VARIANT});
                border: none;
                border-right: 1px solid {ModernColors.BORDER};
                padding: 16px 8px;
                spacing: 4px;
            }}
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
                margin: 3px 0;
                padding: 6px;
            }}
            QToolButton:checked {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ModernColors.PRIMARY},
                    stop:1 {ModernColors.PRIMARY_HOVER});
                border: 1px solid {ModernColors.PRIMARY_HOVER};
                box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
            }}
            QToolButton:hover {{
                background: {ModernColors.SURFACE_HOVER};
                transform: translateX(2px);
            }}
            QToolButton:checked:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ModernColors.PRIMARY_HOVER},
                    stop:1 {ModernColors.PRIMARY});
            }}
            QToolButton:pressed {{
                transform: scale(0.95);
            }}
        """)

    # ---- действия ----
    def choose_color(self):
        selected_items = list(self.canvas.scene.selectedItems())
        focus_item = self.canvas.scene.focusItem()

        dlg = HexColorDialog(self)
        if dlg.exec():
            color = dlg.selected
            if color and color.isValid():
                self.color_btn.set_color(color)
                self.canvas.set_pen_color(color)
                self.text_manager.set_text_color(color)
                self.text_manager.apply_color_to_selected(selected_items, focus_item)

    def copy_to_clipboard(self):
        img = self.canvas.export_image()
        qim = ImageQt.ImageQt(img)
        QApplication.clipboard().setImage(qim)
        self.statusBar().showMessage("✅ Скопировано в буфер обмена", 2000)

    def save_image(self):
        img = self.canvas.export_image()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить изображение", "",
                                              "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)")
        if path:
            if path.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(path)
            self.statusBar().showMessage(f"✅ Сохранено: {Path(path).name}", 3000)

    def ocr_current(self):
        img = self.canvas.export_image()
        if self.ocr_manager.ocr_to_clipboard(img, self):
            self.statusBar().showMessage("🔍 Текст распознан и скопирован", 3000)

    # NEW: Live Text
    def toggle_live_text(self):
        ok = self.live_manager.toggle()
        if ok:
            self.statusBar().showMessage("🔍 Live Text — включено. Выдели мышью область и жми Ctrl+Shift+C", 3500)
        else:
            self.statusBar().showMessage("🔍 Live Text — выключено", 2000)

    def copy_live_text(self):
        """Скопировать выделенный Live-текст. Если нет — OCR всей сцены."""
        if self.live_manager.active and self.live_manager.copy_selection_to_clipboard():
            self.statusBar().showMessage("📋 Текст скопирован (Live)", 2500)
            return
        # Фоллбек: обычный OCR
        img = self.canvas.export_image()
        if self.ocr_manager.ocr_to_clipboard(img, self):
            self.statusBar().showMessage("📋 Текст распознан и скопирован", 2500)

    def _update_collage_enabled(self):
        try:
            has_history = any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(
                HISTORY_DIR.glob("*.jpeg"))
            if hasattr(self, "act_collage"):
                self.act_collage.setEnabled(bool(has_history))
        except Exception:
            pass

    # ---- хоткеи / добавление снимка ----
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected_items = self.canvas.scene.selectedItems()
            for item in selected_items:
                if item != self.canvas.pixmap_item:
                    self.canvas.scene.removeItem(item)
                    if item in self.canvas._undo:
                        self.canvas._undo.remove(item)
            if selected_items:
                self.statusBar().showMessage("🗑️ Удалены выбранные элементы", 2000)
        elif event.modifiers() & Qt.ControlModifier:
            selected_items = [it for it in self.canvas.scene.selectedItems()]
            if selected_items:
                if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                    for it in selected_items:
                        it.setScale(it.scale() * 1.1)
                elif event.key() == Qt.Key_Minus:
                    for it in selected_items:
                        it.setScale(it.scale() * 0.9)
        super().keyPressEvent(event)

    def add_screenshot(self):
        """Новый скриншот через оверлей"""
        try:
            from gui import OverlayManager
            self.setWindowState(self.windowState() | Qt.WindowMinimized)
            self.hide()
            QApplication.processEvents()
            self.overlay_manager = OverlayManager(self.cfg)
            self.overlay_manager.captured.connect(self._on_new_screenshot)
            QTimer.singleShot(25, self.overlay_manager.start)
        except Exception as e:
            self.show()
            QMessageBox.critical(self, "Ошибка", f"Не удалось захватить скриншот: {e}")

    def _on_new_screenshot(self, qimg: QImage):
        """Обработать новый скриншот: добавить отдельным элементом сцены"""
        try:
            self.overlay_manager.close_all()
        except Exception:
            pass
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        QTimer.singleShot(0, lambda: (self.raise_(), self.activateWindow()))
        try:
            save_history(qimage_to_pil(qimg))
        except Exception:
            pass

        pixmap = QPixmap.fromImage(qimg)
        screenshot_item = QGraphicsPixmapItem(pixmap)
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        self.canvas.scene.addItem(screenshot_item)

        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        r = screenshot_item.boundingRect()
        screenshot_item.setPos(view_center.x() - r.width() / 2, view_center.y() - r.height() / 2)
        screenshot_item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        self.canvas._apply_lock_state()
        self.statusBar().showMessage("📸 Новый скриншот добавлен (можно двигать и масштабировать)", 2500)

    # ---- коллаж ----
    def open_collage(self):
        from collage import CollageDialog, compose_collage
        dlg = CollageDialog(self)
        if dlg.exec():
            paths = dlg.selected_images()
            if not paths:
                return
            img = compose_collage(paths, dlg.target_width)
            EditorWindow(ImageQt.ImageQt(img), self.cfg).show()
