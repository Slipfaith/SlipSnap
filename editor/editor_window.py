# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
)

from logic import qimage_to_pil, save_history
from editor.text_tools import TextManager
from editor.live_ocr import LiveTextManager
from editor.editor_logic import EditorLogic

from editor.undo_commands import AddCommand, RemoveCommand, ScaleCommand

from .ui.canvas import Canvas
from .ui.styles import main_window_style
from .ui.color_widgets import HexColorDialog
from .ui.toolbar_factory import create_tools_toolbar, create_actions_toolbar
from .ui.window_utils import size_to_image


class EditorWindow(QMainWindow):
    """Main editor window coordinating UI components."""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")

        min_width = 580
        min_height = 480
        self.setMinimumSize(min_width, min_height)

        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.live_manager = LiveTextManager(self.canvas)
        self.logic = EditorLogic(self.canvas, self.live_manager)

        self.setCentralWidget(self.canvas)
        self.setStyleSheet(main_window_style())

        self._tool_buttons = create_tools_toolbar(self, self.canvas)
        self.color_btn, actions = create_actions_toolbar(self, self.canvas)
        self.act_live = actions['live']
        self.act_new = actions['new']
        self.act_collage = actions['collage']
        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        QTimer.singleShot(0, lambda q=qimg: size_to_image(self, q))

        self.statusBar().showMessage("Готово | Ctrl+N: новый скриншот | Ctrl+K: история | Ctrl+L: Live | Del: удалить | Ctrl +/-: масштаб", 5000)

    # ---- actions ----
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
        self.logic.copy_to_clipboard()
        self.statusBar().showMessage("✅ Скопировано в буфер обмена", 2000)

    def save_image(self):
        name = self.logic.save_image(self)
        if name:
            self.statusBar().showMessage(f"✅ Сохранено: {name}", 3000)

    def toggle_live_text(self):
        ok = self.logic.toggle_live_text()
        if ok:
            self.statusBar().showMessage("🔍 Live Text — включено", 3500)
        else:
            self.statusBar().showMessage("🔍 Live Text — выключено", 2000)

    def _update_collage_enabled(self):
        try:
            if hasattr(self, "act_collage"):
                self.act_collage.setEnabled(self.logic.collage_available())
        except Exception:
            pass

    # ---- key events ----
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected_items = self.canvas.scene.selectedItems()
            for item in selected_items:
                if item != self.canvas.pixmap_item:
                    self.canvas.scene.removeItem(item)
                    self.canvas.undo_stack.push(RemoveCommand(self.canvas.scene, item))
            if selected_items:
                self.statusBar().showMessage("🗑️ Удалены выбранные элементы", 2000)
        elif event.modifiers() & Qt.ControlModifier:
            selected_items = [it for it in self.canvas.scene.selectedItems()]
            if selected_items:
                before = {it: it.scale() for it in selected_items}
                if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                    for it in selected_items:
                        it.setScale(it.scale() * 1.1)
                elif event.key() == Qt.Key_Minus:
                    for it in selected_items:
                        it.setScale(it.scale() * 0.9)
                after = {it: it.scale() for it in selected_items}
                if any(before[it] != after[it] for it in selected_items):
                    self.canvas.undo_stack.push(
                        ScaleCommand({it: (before[it], after[it]) for it in selected_items})
                    )
        super().keyPressEvent(event)

    # ---- screenshots ----
    def add_screenshot(self):
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

    def _rounded_pixmap(self, qimg: QImage, radius: int = 12) -> QPixmap:
        pixmap = QPixmap(qimg.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHints(
            QPainter.Antialiasing
            | QPainter.HighQualityAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, qimg.width(), qimg.height()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, QPixmap.fromImage(qimg))
        painter.end()
        return pixmap

    def _insert_screenshot_item(self, qimg: QImage):
        pixmap = self._rounded_pixmap(qimg)
        screenshot_item = QGraphicsPixmapItem(pixmap)
        screenshot_item.setTransformationMode(Qt.SmoothTransformation)
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        self.canvas.scene.addItem(screenshot_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, screenshot_item))

        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        r = screenshot_item.boundingRect()
        screenshot_item.setPos(view_center.x() - r.width() / 2, view_center.y() - r.height() / 2)
        screenshot_item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        self.canvas._apply_lock_state()

    def _on_new_screenshot(self, qimg: QImage):
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

        self._insert_screenshot_item(qimg)
        self.statusBar().showMessage(
            "📸 Новый скриншот добавлен (можно двигать и масштабировать)", 2500
        )

    # ---- collage ----
    def open_collage(self):
        from collage import CollageDialog

        dlg = CollageDialog(self)
        if dlg.exec():
            paths = dlg.selected_images()
            if not paths:
                return
            added = 0
            for p in paths:
                qimg = QImage(str(p))
                if not qimg.isNull():
                    self._insert_screenshot_item(qimg)
                    added += 1
            if added:
                self.statusBar().showMessage(
                    f"🖼 Добавлено из истории: {added}", 2500
                )

    def closeEvent(self, event):
        try:
            if getattr(self, "live_manager", None):
                self.live_manager.disable()
                try:
                    self.canvas.viewport().removeEventFilter(self.live_manager._filter)
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(event)
