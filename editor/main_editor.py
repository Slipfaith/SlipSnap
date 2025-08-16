# -*- coding: utf-8 -*-
import math
from typing import Optional, List
from pathlib import Path
from PIL import Image, ImageQt

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QColor, QImage, QKeySequence, QPixmap, QAction, QFont,
    QCursor, QTextCursor, QTextCharFormat
)
from PySide6.QtWidgets import (
    QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
    QFileDialog, QMessageBox, QToolBar, QLabel, QWidget, QHBoxLayout,
    QToolButton, QApplication, QColorDialog, QFontDialog, QGraphicsItemGroup,
    QGraphicsTextItem
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

        # Настройки UI
        self.setDragMode(QGraphicsView.ScrollHandDrag)
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
        """Лочим фоновые картинки при активном инструменте рисования."""
        lock = self._tool not in ("none", "select")
        self._set_pixmap_items_interactive(not lock)
        self.setDragMode(QGraphicsView.NoDrag if lock else QGraphicsView.ScrollHandDrag)

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


class EditorWindow(QMainWindow):
    """Главное окно редактора"""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        # Инициализация компонентов
        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.ocr_manager = OCRManager(cfg)

        self.setCentralWidget(self.canvas)
        self._setup_styles()
        self._create_toolbar()

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

    def _create_toolbar(self):
        """Создать панель инструментов"""
        tools_tb = QToolBar("Tools")
        tools_tb.setMovable(False)
        tools_tb.setFloatable(False)
        tools_tb.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea, tools_tb)

        tb = QToolBar("Actions")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        def add_action(toolbar, text, fn, checkable=False, sc=None, icon_text="", show_text=True):
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

        self._tool_buttons = []

        def create_tool(name, tool, icon_text="", sc=None, show_text=True):
            def handler(checked):
                if checked:
                    for other in self._tool_buttons:
                        if other is not btn:
                            other.defaultAction().setChecked(False)
                    self.canvas.set_tool(tool)
                elif all(not b.defaultAction().isChecked() for b in self._tool_buttons):
                    self.canvas.set_tool("select")

            action, btn = add_action(tools_tb, name, handler, True, sc, icon_text, show_text)
            self._tool_buttons.append(btn)
            return action, btn

        # Инструменты на левой панели
        create_tool("Выделение", "select", "→", "S")
        create_tool("Прямоуг.", "rect", "▭", "R", show_text=False)
        create_tool("Эллипс", "ellipse", "○", "E", show_text=False)
        create_tool("Линия", "line", sc="L")
        create_tool("Стрелка", "arrow", "→", "A")
        create_tool("Карандаш", "free", sc="F")
        create_tool("Текст", "text", sc="T")

        # Кнопка выбора цвета линии
        self.color_btn = ColorButton(QColor(255, 80, 80))
        self.color_btn.setToolTip("Цвет линии")
        self.color_btn.clicked.connect(self.choose_draw_color)
        tb.addWidget(self.color_btn)

        # Кнопка выбора шрифта
        font_action, font_btn = add_action(tb, "Шрифт", self.choose_font)
        font_btn.setMinimumWidth(80)
        font_btn.setStyleSheet("""
            QToolButton {
                font-weight: bold;
                background: #f0f8ff;
                border: 1px solid #87ceeb;
            }
            QToolButton:hover {
                background: #e6f3ff;
                border: 1px solid #4682b4;
            }
        """)

        # Цвет текста
        self.text_color_btn = ColorButton(QColor(40, 40, 40))
        self.text_color_btn.setToolTip("Цвет текста")
        self.text_color_btn.clicked.connect(self.choose_text_color)
        tb.addWidget(self.text_color_btn)

        tb.addSeparator()

        self.act_ocr, _ = add_action(tb, "OCR", self.ocr_current, sc="Ctrl+Alt+O", icon_text="📄", show_text=False)
        self.act_new, _ = add_action(tb, "Новый снимок", self.add_screenshot, sc="Ctrl+N", icon_text="📸", show_text=False)
        self.act_collage, _ = add_action(tb, "Коллаж", self.open_collage, sc="Ctrl+K", icon_text="🧩", show_text=False)
        add_action(tb, "Копировать", self.copy_to_clipboard, sc="Ctrl+C", icon_text="📋", show_text=False)
        add_action(tb, "Сохранить", self.save_image, sc="Ctrl+S", icon_text="💾", show_text=False)
        add_action(tb, "Отмена", lambda: self.canvas.undo(), sc="Ctrl+Z", icon_text="↶", show_text=False)

        # Активируем инструмент выделения по умолчанию
        if self._tool_buttons:
            self._tool_buttons[0].defaultAction().setChecked(True)
            self.canvas.set_tool("select")

        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

    def choose_draw_color(self):
        """Выбрать цвет для рисования"""
        color = QColorDialog.getColor(self.color_btn.color, self, "Выберите цвет для рисования")
        if color.isValid():
            self.color_btn.set_color(color)
            self.canvas.set_pen_color(color)

    def choose_text_color(self):
        """Выбрать цвет текста"""
        selected_items = list(self.canvas.scene.selectedItems())
        focus_item = self.canvas.scene.focusItem()

        color = QColorDialog.getColor(self.text_color_btn.color, self, "Выберите цвет текста")
        if color.isValid():
            self.text_color_btn.set_color(color)
            self.text_manager.set_text_color(color)
            self.text_manager.apply_color_to_selected(selected_items, focus_item)

    def choose_font(self):
        """Выбрать шрифт"""
        selected_items = list(self.canvas.scene.selectedItems())
        focus_item = self.canvas.scene.focusItem()

        if self.text_manager.choose_font(self, selected_items, focus_item):
            # Шрифт был изменен успешно
            pass

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
