# -*- coding: utf-8 -*-
import math
from typing import Optional, List
from pathlib import Path
from PIL import Image, ImageQt

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, QTimer, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QImage, QKeySequence, QPixmap, QAction,
    QCursor, QTextCursor, QTextCharFormat, QIcon
)
from PySide6.QtWidgets import (
    QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
    QFileDialog, QMessageBox, QToolBar, QLabel, QWidget, QHBoxLayout,
    QToolButton, QApplication, QGraphicsItemGroup, QGraphicsTextItem,
    QDialog, QGridLayout
)

from logic import pil_to_qpixmap, qimage_to_pil, HISTORY_DIR, save_history
from editor.text_tools import TextManager, EditableTextItem
from editor.ocr_tools import OCRManager


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
        self.setStyleSheet("""
            QGraphicsView { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; }
            QGraphicsView:focus { border: 2px solid #0d6efd; outline: none; }
        """)

        # Инициализация инструментов
        self._tool = "none"
        self._start = QPointF()
        self._tmp: Optional[QGraphicsItem] = None
        self._pen = QPen(QColor(255, 80, 80), 3)
        self._pen.setCapStyle(Qt.RoundCap)
        self._pen.setJoinStyle(Qt.RoundJoin)
        self._undo: List[QGraphicsItem] = []
        self._last_point: Optional[QPointF] = None

        # Создаем кастомные курсоры
        self._create_custom_cursors()
        self._apply_lock_state()

    def _create_custom_cursors(self):
        """Создает кастомные курсоры для инструментов"""
        # Курсор карандаша
        pencil_pixmap = QPixmap(20, 20)
        pencil_pixmap.fill(Qt.transparent)
        painter = QPainter(pencil_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.drawLine(3, 16, 16, 3)
        painter.setPen(QPen(QColor(200, 150, 100), 1))
        painter.drawEllipse(15, 2, 4, 4)
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        painter.drawLine(2, 17, 4, 15)
        painter.end()
        self._pencil_cursor = QCursor(pencil_pixmap, 3, 16)

        # Черный курсор для выделения
        select_pixmap = QPixmap(16, 16)
        select_pixmap.fill(Qt.transparent)
        painter = QPainter(select_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QColor(0, 0, 0))
        # Рисуем стрелку
        points = [
            QPointF(1, 1), QPointF(1, 11), QPointF(4, 8), QPointF(7, 11),
            QPointF(9, 9), QPointF(6, 6), QPointF(11, 1)
        ]
        painter.drawPolygon(points)
        painter.end()
        self._select_cursor = QCursor(select_pixmap, 1, 1)

    def _set_pixmap_items_interactive(self, enabled: bool):
        """Включить/выключить перетаскивание и прием мыши у всех QGraphicsPixmapItem."""
        for it in self.scene.items():
            if isinstance(it, QGraphicsPixmapItem):
                it.setFlag(QGraphicsItem.ItemIsMovable, enabled)
                it.setAcceptedMouseButtons(Qt.AllButtons if enabled else Qt.NoButton)
                if not enabled and it.isSelected():
                    it.setSelected(False)

    def _apply_lock_state(self):
        """Лочим фоновые картинки при активном инструменте рисования.
        Вьюшка никогда сама не скроллит (NoDrag всегда)."""
        lock = self._tool not in ("none", "select")
        self._set_pixmap_items_interactive(not lock)
        self.setDragMode(QGraphicsView.NoDrag)

    def set_tool(self, tool: str):
        """Установить текущий инструмент"""
        # Завершаем редактирование текста при смене инструмента
        if hasattr(self, '_text_manager') and self._text_manager:
            self._text_manager.finish_current_editing()

        self._tool = tool
        if tool == "select":
            self.viewport().setCursor(self._select_cursor)
        elif tool in {"rect", "ellipse", "line", "arrow"}:
            self.viewport().setCursor(Qt.CrossCursor)
        elif tool == "free":
            self.viewport().setCursor(self._pencil_cursor)
        elif tool == "text":
            self.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)
        self._apply_lock_state()

    def set_text_manager(self, text_manager):
        """Установить менеджер текста"""
        self._text_manager = text_manager

    def set_pen_width(self, w: int):
        """Установить толщину пера"""
        self._pen.setWidth(w)

    def set_pen_color(self, color: QColor):
        """Установить цвет пера"""
        self._pen.setColor(color)

    def export_image(self) -> Image.Image:
        """Экспортировать изображение"""
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
        """Отменить последнее действие"""
        if self._undo:
            item = self._undo.pop()
            self.scene.removeItem(item)

    def wheelEvent(self, event):
        """Обработка события колеса мыши для масштабирования"""
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
        """Обработка нажатия мыши"""
        if event.button() == Qt.LeftButton and self._tool not in ("none", "select"):
            self._start = self.mapToScene(event.position().toPoint())
            if self._tool == "text":
                # Создаем текстовый элемент на месте клика
                if hasattr(self, '_text_manager') and self._text_manager:
                    item = self._text_manager.create_text_item(self._start)
                    if item:
                        self._undo.append(item)
                event.accept()
                return
            elif self._tool == "free":
                self._last_point = self._start
                self._tmp = None
            else:
                self._tmp = None
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Обработка движения мыши"""
        if (event.buttons() & Qt.LeftButton) and self._tool not in ("none", "select"):
            pos = self.mapToScene(event.position().toPoint())
            if self._tool == "free":
                if self._last_point is not None:
                    line = self.scene.addLine(QLineF(self._last_point, pos), self._pen)
                    line.setFlag(QGraphicsItem.ItemIsSelectable, True)
                    self._undo.append(line)
                    self._last_point = pos
            elif self._tool != "text":  # Не обрабатываем движение для текста
                if self._tmp:
                    self.scene.removeItem(self._tmp)
                self._tmp = self._preview_item(self._tool, self._start, pos, self._pen)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания мыши"""
        if event.button() == Qt.LeftButton and self._tool not in ("none", "select", "text"):
            if self._tool == "free":
                self._last_point = None
            else:
                if self._tmp:
                    self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
                    self._undo.append(self._tmp)
                    self._tmp = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _preview_item(self, tool: str, start: QPointF, end: QPointF, pen: QPen) -> QGraphicsItem:
        """Создать предварительный элемент для рисования"""
        if tool == "rect":
            r = QRectF(start, end).normalized()
            item = self.scene.addRect(r, pen)
        elif tool == "ellipse":
            r = QRectF(start, end).normalized()
            item = self.scene.addEllipse(r, pen)
        elif tool == "line":
            item = self.scene.addLine(QLineF(start, end), pen)
        elif tool == "arrow":
            item = self._add_arrow(start, end, pen)
        else:
            item = self.scene.addLine(QLineF(start, end), pen)
        return item

    def _add_arrow(self, start: QPointF, end: QPointF, pen: QPen) -> QGraphicsItem:
        """Создать стрелку"""
        # Создаем группу для всех частей стрелки
        group = QGraphicsItemGroup()

        # Основная линия
        line = self.scene.addLine(QLineF(start, end), pen)
        group.addToGroup(line)

        # Наконечник стрелки
        v = end - start
        length = (v.x() ** 2 + v.y() ** 2) ** 0.5
        if length >= 1:
            ux, uy = v.x() / length, v.y() / length
            head = 12
            left = QPointF(end.x() - ux * head - uy * head * 0.5, end.y() - uy * head + ux * head * 0.5)
            right = QPointF(end.x() - ux * head + uy * head * 0.5, end.y() - uy * head - ux * head * 0.5)

            left_line = self.scene.addLine(QLineF(end, left), pen)
            right_line = self.scene.addLine(QLineF(end, right), pen)

            group.addToGroup(left_line)
            group.addToGroup(right_line)

        self.scene.addItem(group)
        return group


class ColorButton(QToolButton):
    """Кнопка выбора цвета"""

    def __init__(self, color: QColor):
        super().__init__()
        self.color = color
        self.setFixedSize(32, 24)
        self.update_color()

    def update_color(self):
        """Обновить отображение цвета"""
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {self.color.name()};
                border: 2px solid #ccc;
                border-radius: 4px;
            }}
            QToolButton:hover {{
                border: 2px solid #0d6efd;
            }}
        """)

    def set_color(self, color: QColor):
        """Установить новый цвет"""
        self.color = color
        self.update_color()


class HexColorDialog(QDialog):
    """Миниатюрная гексагональная палитра цветов"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup)
        self.selected = None

        colors = [
            "#000000", "#808080", "#FF0000",
            "#FFA500", "#FFFF00", "#008000", "#00FFFF",
            "#0000FF", "#800080", "#FFFFFF"
        ]
        positions = [
            (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 1), (2, 2), (2, 3)
        ]

        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        for pos, col in zip(positions, colors):
            btn = QToolButton()
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(
                f"QToolButton{{background:{col}; border:1px solid #555; border-radius:10px;}}"
                "QToolButton:hover{border:2px solid #0d6efd;}"
            )
            btn.clicked.connect(lambda _=None, c=col: self._choose(c))
            layout.addWidget(btn, *pos)

    def _choose(self, color_str):
        self.selected = QColor(color_str)
        self.accept()


class EditorWindow(QMainWindow):
    """Главное окно редактора"""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")
        self.setMinimumSize(360, 240)

        # Инициализация компонентов
        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.ocr_manager = OCRManager(cfg)
        self.setCentralWidget(self.canvas)
        self._setup_styles()
        self._create_toolbar()

        # Подогнать окно под картинку ПОСЛЕ создания сцены и тулбаров
        QTimer.singleShot(0, lambda q=qimg: self._size_to_image(q))

        self.statusBar().showMessage(
            "Готово | Ctrl+N: новый скриншот | Ctrl+K: коллаж | Ctrl+Alt+O: OCR | Del: удалить | Ctrl +/-: масштаб")

    def _setup_styles(self):
        """Настроить стили интерфейса"""
        self.setStyleSheet("""
            QMainWindow { background: #ffffff; }
            QToolBar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8f9fa);
                       border: none; border-bottom: 1px solid #e9ecef; spacing: 8px; padding: 8px 12px; font-weight: 500; }
            QToolButton { background: transparent; border: none; padding: 6px 8px; border-radius: 8px; }
            QToolButton:hover { background: #eef4ff; }
            QToolButton:checked { background: #0d6efd; color: white; border: 1px solid #0d47a1; }
            QLabel { color: #6c757d; font-size: 12px; font-weight: 500; margin: 0 4px; }
            QToolBar::separator { background: #e9ecef; width: 1px; margin: 4px 8px; }
        """)

    def _size_to_image(self, qimg: QImage):
        """Подогнать размер окна под размер картинки и центрировать."""
        # Убедимся, что сцена знает свой bbox
        self.canvas.scene.setSceneRect(self.canvas.scene.itemsBoundingRect())

        # Размеры панели инструментов (слева) и верхней панели
        toolbars = self.findChildren(QToolBar)
        left_w = sum(tb.sizeHint().width() for tb in toolbars if tb.orientation() == Qt.Vertical)
        top_h = sum(tb.sizeHint().height() for tb in toolbars if tb.orientation() == Qt.Horizontal)
        status_h = self.statusBar().sizeHint().height() if self.statusBar() else 0

        # Доступная область экрана
        screen = self.screen() or QApplication.primaryScreen()
        ag = screen.availableGeometry()

        # Целевые размеры: картинка 1:1 + панели + небольшой запас
        target_w = qimg.width() + left_w + 24
        target_h = qimg.height() + top_h + status_h + 24

        # Не раздуваем окно больше 90% экрана, и не меньше минимума
        target_w = max(self.minimumWidth(), min(target_w, int(ag.width() * 0.9)))
        target_h = max(self.minimumHeight(), min(target_h, int(ag.height() * 0.9)))

        self.resize(target_w, target_h)

        # Центрируем картинку во вью (на всякий случай) и окно на экране
        self.canvas.centerOn(self.canvas.pixmap_item)
        self.move(ag.x() + (ag.width() - self.width()) // 2,
                  ag.y() + (ag.height() - self.height()) // 2)

    def _create_toolbar(self):
        """Создать панель инструментов — только иконки!"""
        tools_tb = QToolBar("Tools")
        tools_tb.setMovable(False)
        tools_tb.setFloatable(False)
        tools_tb.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea, tools_tb)

        # Минималистичные иконки для инструментов
        def make_icon_rect():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawRect(4, 4, 20, 20)
            p.end()
            return QIcon(pm)

        def make_icon_ellipse():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawEllipse(4, 4, 20, 20)
            p.end()
            return QIcon(pm)

        def make_icon_line():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawLine(6, 22, 22, 6)
            p.end()
            return QIcon(pm)

        def make_icon_arrow():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawLine(6, 22, 20, 8)
            p.drawLine(20, 8, 15, 11)
            p.drawLine(20, 8, 18, 14)
            p.end()
            return QIcon(pm)

        def make_icon_pencil():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawLine(6, 22, 22, 6)
            p.setPen(QColor(200, 150, 100))
            p.drawEllipse(20, 4, 3, 3)
            p.end()
            return QIcon(pm)

        def make_icon_text():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            font = p.font()
            font.setBold(True)
            font.setPointSize(18)
            p.setFont(font)
            p.drawText(pm.rect(), Qt.AlignCenter, "T")
            p.end()
            return QIcon(pm)

        def make_icon_select():
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor(80, 80, 80))
            p.drawPolygon([QPointF(6, 6), QPointF(6, 22), QPointF(12, 18), QPointF(18, 22), QPointF(22, 18), QPointF(14, 12), QPointF(22, 6)])
            p.end()
            return QIcon(pm)

        self._tool_buttons = []
        def add_tool(tool, icon, tooltip):
            btn = QToolButton()
            btn.setIcon(icon)
            btn.setIconSize(QSize(28, 28))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedSize(36, 36)
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
        add_tool("text", make_icon_text(), "Текст")

        self._tool_buttons[0].setChecked(True)
        self.canvas.set_tool("select")

        # Остальная панель — как у тебя была, не меняю!
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

        self.color_btn = ColorButton(QColor(255, 80, 80))
        self.color_btn.setToolTip("Цвет")
        self.color_btn.clicked.connect(self.choose_color)
        tb.addWidget(self.color_btn)

        tb.addSeparator()

        self.act_ocr, _ = add_action(tb, "OCR", self.ocr_current, sc="Ctrl+Alt+O", icon_text="📄", show_text=False)
        self.act_new, _ = add_action(tb, "Новый снимок", self.add_screenshot, sc="Ctrl+N", icon_text="📸", show_text=False)
        self.act_collage, _ = add_action(tb, "Коллаж", self.open_collage, sc="Ctrl+K", icon_text="🧩", show_text=False)
        add_action(tb, "Копировать", self.copy_to_clipboard, sc="Ctrl+C", icon_text="📋", show_text=False)
        add_action(tb, "Сохранить", self.save_image, sc="Ctrl+S", icon_text="💾", show_text=False)
        add_action(tb, "Отмена", lambda: self.canvas.undo(), sc="Ctrl+Z", icon_text="↶", show_text=False)

        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        # Минималистичный стиль только для тулбара инструментов!
        tools_tb.setStyleSheet("""
            QToolBar {
                background: #f9f9fb;
                border: none;
                padding: 8px;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                margin: 2px 0;
            }
            QToolButton:checked {
                background: #e7f0fa;
                border: 1px solid #1976d2;
            }
            QToolButton:hover {
                background: #e7f0fa;
            }
        """)

    def choose_color(self):
        """Выбрать цвет"""
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
        """Копировать в буфер обмена"""
        img = self.canvas.export_image()
        qim = ImageQt.ImageQt(img)
        QApplication.clipboard().setImage(qim)
        self.statusBar().showMessage("✅ Скопировано в буфер обмена", 2000)

    def save_image(self):
        """Сохранить изображение"""
        img = self.canvas.export_image()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить изображение", "",
                                              "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)")
        if path:
            if path.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(path)
            self.statusBar().showMessage(f"✅ Сохранено: {Path(path).name}", 3000)

    def ocr_current(self):
        """Выполнить OCR текущего изображения"""
        img = self.canvas.export_image()
        if self.ocr_manager.ocr_to_clipboard(img, self):
            self.statusBar().showMessage("🔍 Текст распознан и скопирован", 3000)

    def _update_collage_enabled(self):
        """Обновить доступность функции коллажа"""
        try:
            has_history = any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(
                HISTORY_DIR.glob("*.jpeg"))
            if hasattr(self, "act_collage"):
                self.act_collage.setEnabled(bool(has_history))
        except Exception:
            pass

    def keyPressEvent(self, event):
        """Обработка нажатий клавиш"""
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
        """Добавить новый скриншот"""
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
        """Обработать новый скриншот"""
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

    def open_collage(self):
        """Открыть диалог создания коллажа"""
        from collage import CollageDialog, compose_collage
        dlg = CollageDialog(self)
        if dlg.exec():
            paths = dlg.selected_images()
            if not paths:
                return
            img = compose_collage(paths, dlg.target_width)
            EditorWindow(ImageQt.ImageQt(img), self.cfg).show()
