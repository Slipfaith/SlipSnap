# -*- coding: utf-8 -*-
from typing import Optional, List, Dict
from pathlib import Path
import pytesseract
from PIL import Image, ImageQt

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, QSize, QTimer
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QImage,
    QKeySequence,
    QPixmap,
    QAction,
    QFont,
    QCursor,
    QUndoStack,
    QUndoCommand,
)
from PySide6.QtWidgets import (
    QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
    QFileDialog, QMessageBox, QToolBar, QLabel, QSpinBox, QWidget, QHBoxLayout,
    QVBoxLayout, QFrame, QToolButton, QSizePolicy, QApplication
)

from logic import pil_to_qpixmap, qimage_to_pil, HISTORY_DIR, save_history


class AddCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, item: QGraphicsItem):
        super().__init__("add")
        self.scene = scene
        self.item = item
        self._done = True

    def undo(self):
        self.scene.removeItem(self.item)
        self._done = False

    def redo(self):
        if not self._done:
            self.scene.addItem(self.item)
            self._done = True


class DeleteCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, item: QGraphicsItem):
        super().__init__("delete")
        self.scene = scene
        self.item = item

    def undo(self):
        self.scene.addItem(self.item)

    def redo(self):
        self.scene.removeItem(self.item)


class MoveCommand(QUndoCommand):
    def __init__(self, item: QGraphicsItem, old_pos: QPointF, new_pos: QPointF):
        super().__init__("move")
        self.item = item
        self.old = old_pos
        self.new = new_pos
        self._done = True

    def undo(self):
        self.item.setPos(self.old)
        self._done = False

    def redo(self):
        if not self._done:
            self.item.setPos(self.new)
            self._done = True


class ScaleCommand(QUndoCommand):
    def __init__(self, item: QGraphicsItem, old_scale: float, new_scale: float):
        super().__init__("scale")
        self.item = item
        self.old = old_scale
        self.new = new_scale
        self._done = True

    def undo(self):
        self.item.setScale(self.old)
        self._done = False

    def redo(self):
        if not self._done:
            self.item.setScale(self.new)
            self._done = True


class Canvas(QGraphicsView):
    def __init__(self, image: QImage):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        # Первый слой тоже редактируемый
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.pixmap_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.pixmap_item.setZValue(0)
        self.scene.addItem(self.pixmap_item)

        self.setDragMode(QGraphicsView.ScrollHandDrag)

        self.setStyleSheet("""
            QGraphicsView {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
            }
            QGraphicsView:focus {
                border: 2px solid #0d6efd;
                outline: none;
            }
        """)

        self._tool = "none"
        self._start = QPointF()
        self._tmp: Optional[QGraphicsItem] = None

        self._pen = QPen(QColor(255, 80, 80), 3)
        self._pen.setCapStyle(Qt.RoundCap)
        self._pen.setJoinStyle(Qt.RoundJoin)

        self._font_px = 18
        self.undo_stack = QUndoStack(self)
        self._last_point: Optional[QPointF] = None
        self._move_start: Dict[QGraphicsItem, QPointF] = {}

    def set_tool(self, tool: str):
        self._tool = tool
        if tool in {"rect", "ellipse", "line", "arrow", "free"}:
            self.viewport().setCursor(Qt.CrossCursor)
        elif tool == "text":
            self.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

    def set_pen_width(self, w: int): self._pen.setWidth(w)
    def set_font_size(self, px: int): self._font_px = px

    # --- Экспорт ---
    def export_image(self) -> Image.Image:
        rect = self.scene.itemsBoundingRect()
        img = QImage(int(rect.width()), int(rect.height()), QImage.Format_RGBA8888)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.scene.render(p, QRectF(img.rect()), rect)
        p.end()
        return ImageQt.ImageQt.toImage(img).copy() if hasattr(ImageQt.ImageQt, "toImage") else ImageQt.ImageQt(img)

    # Масштабирование выбранных элементов: Ctrl + колесо
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            selected = self.scene.selectedItems()
            if selected:
                factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
                for it in selected:
                    old = it.scale()
                    new = old * factor
                    it.setScale(new)
                    self.undo_stack.push(ScaleCommand(it, old, new))
                event.accept()
                return
        super().wheelEvent(event)

    # --- Мышь/отрисовка ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._tool == "none":
                self._move_start = {it: it.pos() for it in self.scene.selectedItems()}
            else:
                self._start = self.mapToScene(event.position().toPoint())
                if self._tool == "text":
                    from PySide6.QtWidgets import QInputDialog
                    text, ok = QInputDialog.getText(self, "Текст", "Введите текст:")
                    if ok and text:
                        item = self._add_text_item(text, self._start)
                        self.undo_stack.push(AddCommand(self.scene, item))
                    return
                elif self._tool == "free":
                    self._last_point = self._start
                    self._tmp = None
                else:
                    self._tmp = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self._tool != "none":
            pos = self.mapToScene(event.position().toPoint())
            if self._tool == "free":
                if self._last_point is not None:
                    line = self.scene.addLine(QLineF(self._last_point, pos), self._pen)
                    line.setFlag(QGraphicsItem.ItemIsSelectable, True)
                    line.setFlag(QGraphicsItem.ItemIsMovable, True)
                    self.undo_stack.push(AddCommand(self.scene, line))
                    self._last_point = pos
            else:
                if self._tmp:
                    self.scene.removeItem(self._tmp)
                self._tmp = self._preview_item(self._tool, self._start, pos, self._pen)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._tool == "none":
                for item, old_pos in self._move_start.items():
                    new_pos = item.pos()
                    if old_pos != new_pos:
                        self.undo_stack.push(MoveCommand(item, old_pos, new_pos))
                self._move_start.clear()
            else:
                if self._tool == "free":
                    self._last_point = None
                else:
                    if self._tmp:
                        self._tmp.setFlag(QGraphicsItem.ItemIsSelectable, True)
                        self._tmp.setFlag(QGraphicsItem.ItemIsMovable, True)
                        self.undo_stack.push(AddCommand(self.scene, self._tmp))
                        self._tmp = None
        super().mouseReleaseEvent(event)

    def _preview_item(self, tool: str, start: QPointF, end: QPointF, pen: QPen) -> QGraphicsItem:
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
        line = self.scene.addLine(QLineF(start, end), pen)
        v = end - start
        length = (v.x() ** 2 + v.y() ** 2) ** 0.5
        if length < 1:
            return line
        ux, uy = v.x() / length, v.y() / length
        head = 12
        left = QPointF(
            end.x() - ux * head - uy * head * 0.5,
            end.y() - uy * head + ux * head * 0.5,
        )
        right = QPointF(
            end.x() - ux * head + uy * head * 0.5,
            end.y() - uy * head - ux * head * 0.5,
        )
        l1 = self.scene.addLine(QLineF(end, left), pen)
        l2 = self.scene.addLine(QLineF(end, right), pen)
        group = self.scene.createItemGroup([line, l1, l2])
        return group

    def _add_text_item(self, text: str, pos: QPointF) -> QGraphicsItem:
        from PySide6.QtWidgets import QGraphicsTextItem
        it = QGraphicsTextItem(text)
        f = QFont(); f.setPointSize(self._font_px)
        it.setFont(f)
        it.setDefaultTextColor(QColor(40, 40, 40))
        it.setPos(pos)
        it.setTextInteractionFlags(Qt.TextEditorInteraction)
        it.setFlag(QGraphicsItem.ItemIsMovable, True)
        it.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.scene.addItem(it)
        return it


class EditorWindow(QMainWindow):
    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")

        self.setMinimumSize(700, 500)
        self.resize(900, 650)

        self.setStyleSheet("""
            QMainWindow { background: #ffffff; }
            QToolBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f8f9fa);
                border: none;
                border-bottom: 1px solid #e9ecef;
                spacing: 8px;
                padding: 8px 12px;
                font-weight: 500;
            }
            QToolButton { background: transparent; border: none; padding: 6px 8px; border-radius: 8px; }
            QToolButton:hover { background: #eef4ff; }
            QToolButton:checked { background: #0d6efd; color: white; border: 1px solid #0d47a1; }
            QLabel { color: #6c757d; font-size: 12px; font-weight: 500; margin: 0 4px; }
            QSpinBox { background: white; border: 1px solid #ced4da; border-radius: 4px; padding: 4px 8px; color: #495057; font-size: 13px; min-width: 60px; }
            QSpinBox:hover { border: 1px solid #80bdff; }
            QSpinBox:focus { border: 2px solid #0d6efd; outline: none; }
            QToolBar::separator { background: #e9ecef; width: 1px; margin: 4px 8px; }
        """)

        self.canvas = Canvas(qimg)
        self.setCentralWidget(self.canvas)

        self._create_toolbar()

        self.statusBar().showMessage("Готово | Ctrl+N: новый скриншот | Ctrl+K: коллаж | Ctrl+Alt+O: OCR | Del: удалить | Ctrl +/-: масштаб")

    def _create_toolbar(self):
        tb = QToolBar("Tools")
        tb.setMovable(False); tb.setFloatable(False)
        self.addToolBar(tb)

        def add_action(text, fn, checkable=False, sc=None, icon_text=""):
            a = QAction(text, self)
            a.setCheckable(checkable)
            if sc: a.setShortcut(QKeySequence(sc))
            # регистрируем action на окне + WindowShortcut + глотаем bool
            self.addAction(a)
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(fn if checkable else (lambda _checked=False: fn()))
            btn = QToolButton(); btn.setDefaultAction(a)
            btn.setText(f"{icon_text} {text}" if icon_text else text)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            tb.addWidget(btn)
            return a, btn

        self._tool_buttons = []

        def create_tool(name, tool, icon_text="", sc=None):
            def handler(checked):
                if checked:
                    for other in self._tool_buttons:
                        if other is not btn:
                            other.defaultAction().setChecked(False)
                    self.canvas.set_tool(tool)
                elif all(not b.defaultAction().isChecked() for b in self._tool_buttons):
                    self.canvas.set_tool("none")
            action, btn = add_action(name, handler, True, sc, icon_text)
            self._tool_buttons.append(btn)
            return action, btn

        # Инструменты рисования
        create_tool("Прямоуг.", "rect", "▭", "R")
        create_tool("Эллипс", "ellipse", "◯", "E")
        create_tool("Линия", "line", "／", "L")
        create_tool("Стрелка", "arrow", "➤", "A")
        create_tool("Карандаш", "free", "✎", "F")
        create_tool("Текст", "text", "📝", "T")

        tb.addSeparator()
        undo_action = self.canvas.undo_stack.createUndoAction(self, "Отмена")
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.setShortcutContext(Qt.WindowShortcut)
        self.addAction(undo_action)
        undo_btn = QToolButton(); undo_btn.setDefaultAction(undo_action)
        undo_btn.setText("↶ Отмена")
        undo_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addWidget(undo_btn)

        redo_action = self.canvas.undo_stack.createRedoAction(self, "Повтор")
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.setShortcutContext(Qt.WindowShortcut)
        self.addAction(redo_action)
        redo_btn = QToolButton(); redo_btn.setDefaultAction(redo_action)
        redo_btn.setText("↷ Повтор")
        redo_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addWidget(redo_btn)

        tb.addSeparator()
        add_action("Копировать", self.copy_to_clipboard, sc="Ctrl+C", icon_text="📋")
        add_action("Сохранить", self.save_image, sc="Ctrl+S", icon_text="💾")
        tb.addSeparator()
        self.act_new, _ = add_action("Новый снимок", self.add_screenshot, sc="Ctrl+N", icon_text="📸")
        self.act_ocr, _ = add_action("OCR", self.ocr_current, sc="Ctrl+Alt+O", icon_text="🔎")
        self.act_collage, _ = add_action("Коллаж", self.open_collage, sc="Ctrl+K", icon_text="🧩")
        tb.addSeparator()

        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

    def copy_to_clipboard(self):
        img = self.canvas.export_image()
        qim = ImageQt.ImageQt(img)
        QApplication.clipboard().setImage(qim)
        self.statusBar().showMessage("✅ Скопировано в буфер обмена", 2000)

    def save_image(self):
        img = self.canvas.export_image()
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить изображение", "",
            "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)"
        )
        if path:
            if path.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(path)
            self.statusBar().showMessage(f"✅ Сохранено: {Path(path).name}", 3000)

    def _update_collage_enabled(self):
        try:
            has_history = any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(HISTORY_DIR.glob("*.jpeg"))
            if hasattr(self, "act_collage"):
                self.act_collage.setEnabled(bool(has_history))
        except Exception:
            pass

    def ocr_current(self):
        tpath = self.cfg.get("tesseract_path") or ""
        if tpath:
            pytesseract.pytesseract.tesseract_cmd = tpath
        try:
            text = pytesseract.image_to_string(self.canvas.export_image())
        except Exception as e:
            QMessageBox.warning(self, "OCR", f"Ошибка OCR: {e}\n\nПроверьте установку Tesseract.", QMessageBox.Ok)
            return
        QApplication.clipboard().setText(text or "")
        self.statusBar().showMessage("🔎 Текст распознан и скопирован", 3000)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected_items = [it for it in self.canvas.scene.selectedItems() if it != self.canvas.pixmap_item]
            for item in selected_items:
                self.canvas.undo_stack.push(DeleteCommand(self.canvas.scene, item))
            if selected_items:
                self.statusBar().showMessage("🗑️ Удалены выбранные элементы", 2000)
        elif event.modifiers() & Qt.ControlModifier:
            selected_items = [it for it in self.canvas.scene.selectedItems()]
            if selected_items:
                if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                    factor = 1.1
                elif event.key() == Qt.Key_Minus:
                    factor = 0.9
                else:
                    factor = None
                if factor is not None:
                    for it in selected_items:
                        old = it.scale()
                        new = old * factor
                        it.setScale(new)
                        self.canvas.undo_stack.push(ScaleCommand(it, old, new))
        super().keyPressEvent(event)

    def add_screenshot(self):
        """Добавляет новый скриншот поверх текущего изображения (окно скрывается сразу)."""
        try:
            from gui import OverlayManager

            # 1) мгновенно убираем окно с экрана
            self.setWindowState(self.windowState() | Qt.WindowMinimized)
            self.hide()
            QApplication.processEvents()

            # 2) готовим оверлей и запускаем в следующий тик
            self.overlay_manager = OverlayManager(self.cfg)
            self.overlay_manager.captured.connect(self._on_new_screenshot)
            QTimer.singleShot(25, self.overlay_manager.start)  # короткая пауза для гарантии скрытия

        except Exception as e:
            self.show()
            QMessageBox.critical(self, "Ошибка", f"Не удалось захватить скриншот: {e}")

    def _on_new_screenshot(self, qimg: QImage):
        """Обработчик получения нового скриншота: закрыть оверлеи, вернуть окно, добавить слой."""
        try:
            self.overlay_manager.close_all()
        except Exception:
            pass

        # --- Надёжный возврат окна на передний план ---
        # снимаем минимизацию, показываем, поднимаем и активируем окно
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        # дубль через тик — на случай гонки с закрытием оверлея
        QTimer.singleShot(0, lambda: (self.raise_(), self.activateWindow()))

        # Сохраняем в историю (для «Коллажа»)
        try:
            save_history(qimage_to_pil(qimg))
        except Exception:
            pass

        # Добавляем новый слой
        pixmap = QPixmap.fromImage(qimg)
        screenshot_item = QGraphicsPixmapItem(pixmap)
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        self.canvas.scene.addItem(screenshot_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, screenshot_item))

        # Центрируем и выбираем слой, отдаём фокус канвасу
        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        r = screenshot_item.boundingRect()
        screenshot_item.setPos(view_center.x() - r.width() / 2, view_center.y() - r.height() / 2)
        screenshot_item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)

        self._update_collage_enabled()
        self.statusBar().showMessage("📸 Новый скриншот добавлен (можно двигать и масштабировать)", 2500)

    def open_collage(self):
        """Открывает диалог для создания коллажа из истории скриншотов"""
        from collage import CollageDialog, compose_collage
        dlg = CollageDialog(self)
        if dlg.exec():
            paths = dlg.selected_images()
            if not paths:
                return
            img = compose_collage(paths, dlg.target_width)
            EditorWindow(ImageQt.ImageQt(img), self.cfg).show()

    def closeEvent(self, event):
        try:
            if hasattr(self, "live_manager"):
                self.live_manager.disable()
                QApplication.instance().removeEventFilter(self.live_manager)
        except Exception:
            pass
        super().closeEvent(event)
