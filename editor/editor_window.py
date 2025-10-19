# -*- coding: utf-8 -*-

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
)

from logic import APP_NAME, APP_VERSION, qimage_to_pil, save_history
from editor.text_tools import TextManager
from editor.editor_logic import EditorLogic
from editor.image_utils import images_from_mime

from editor.undo_commands import AddCommand, RemoveCommand, ScaleCommand

from .ui.canvas import Canvas
from .ui.styles import main_window_style
from .ui.color_widgets import HexColorDialog
from .ui.toolbar_factory import create_tools_toolbar, create_actions_toolbar
from .ui.window_utils import size_to_image
from .ui.meme_library_dialog import MemeLibraryDialog


class EditorWindow(QMainWindow):
    """Main editor window with modern light design."""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")

        min_width = 680
        min_height = 540
        self.setMinimumSize(min_width, min_height)

        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.logic = EditorLogic(self.canvas)

        self.setCentralWidget(self.canvas)
        self._apply_modern_stylesheet()
        self.canvas.imageDropped.connect(self._insert_screenshot_item)

        self._tool_buttons = create_tools_toolbar(self, self.canvas)
        self.color_btn, actions, action_buttons = create_actions_toolbar(self, self.canvas)
        self.act_new = actions['new']
        self.act_collage = actions['collage']
        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        self.shortcut_collage = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self.shortcut_collage.activated.connect(lambda: self.add_screenshot(collage=True))

        QTimer.singleShot(0, lambda q=qimg: size_to_image(self, q))

        self.statusBar().showMessage(
            "◉ Готово | Ctrl+N: новый скриншот | Ctrl+Shift+N: коллаж | Ctrl+K: история | Del: удалить | Ctrl +/-: масштаб",
            5000,
        )

        self._meme_library_dialog = MemeLibraryDialog(self)
        self._meme_library_dialog.memeSelected.connect(self._insert_meme_from_library)

        # Меню справки с горячими клавишами
        help_menu = self.menuBar().addMenu("Справка")
        act_shortcuts = help_menu.addAction("⌘ Горячие клавиши")
        act_shortcuts.triggered.connect(self.show_shortcuts)
        act_about = help_menu.addAction("ⓘ О программе")
        act_about.triggered.connect(self.show_about)

    def _apply_modern_stylesheet(self):
        """Apply modern light theme with clean design."""
        self.setStyleSheet("""
            QMainWindow {
                background: #f8f9fa;
            }

            QMenuBar {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff,
                    stop:1 #f5f6f7
                );
                color: #1f2937;
                border: none;
                border-bottom: 1px solid #e5e7eb;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 500;
            }

            QMenuBar::item {
                background: transparent;
                padding: 8px 16px;
                border-radius: 8px;
                margin: 2px;
                color: #374151;
            }

            QMenuBar::item:selected {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e0e7ff,
                    stop:1 #dbeafe
                );
                color: #1e40af;
            }

            QMenuBar::item:pressed {
                background: #bfdbfe;
            }

            QMenu {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                padding: 8px;
                color: #1f2937;
            }

            QMenu::item {
                padding: 10px 24px 10px 12px;
                border-radius: 8px;
                margin: 2px 4px;
                font-size: 13px;
                color: #374151;
            }

            QMenu::item:selected {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #dbeafe,
                    stop:1 #e0e7ff
                );
                color: #1e40af;
            }

            QMenu::separator {
                height: 1px;
                background: #e5e7eb;
                margin: 6px 8px;
            }

            QToolBar {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff,
                    stop:1 #fafbfc
                );
                border: none;
                border-bottom: 1px solid #e5e7eb;
                spacing: 6px;
                padding: 10px 12px;
            }

            QToolBar::separator {
                width: 1px;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(229, 231, 235, 0),
                    stop:0.5 #d1d5db,
                    stop:1 rgba(229, 231, 235, 0)
                );
                margin: 6px 10px;
            }

            QToolButton {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                padding: 9px;
                color: #374151;
                font-weight: 500;
                min-width: 38px;
                min-height: 38px;
            }

            QToolButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #dbeafe,
                    stop:1 #bfdbfe
                );
                border: 1px solid #93c5fd;
                color: #1e40af;
            }

            QToolButton:pressed {
                background: #bfdbfe;
                border: 1px solid #60a5fa;
                padding: 10px 8px 8px 10px;
            }

            QToolButton:checked {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #dbeafe,
                    stop:1 #bfdbfe
                );
                border: 1px solid #60a5fa;
                color: #1e40af;
                font-weight: 600;
            }

            QToolButton:disabled {
                background: #f3f4f6;
                border: 1px solid #e5e7eb;
                color: #9ca3af;
            }

            QStatusBar {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #fafbfc,
                    stop:1 #f3f4f6
                );
                color: #6b7280;
                border-top: 1px solid #e5e7eb;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }

            QStatusBar::item {
                border: none;
            }

            QMessageBox {
                background: #ffffff;
            }

            QMessageBox QLabel {
                color: #1f2937;
                font-size: 13px;
                padding: 8px;
            }

            QMessageBox QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3b82f6,
                    stop:1 #2563eb
                );
                border: 1px solid #1d4ed8;
                border-radius: 8px;
                padding: 10px 24px;
                color: white;
                font-weight: 600;
                min-width: 80px;
            }

            QMessageBox QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #60a5fa,
                    stop:1 #3b82f6
                );
            }

            QMessageBox QPushButton:pressed {
                background: #2563eb;
                padding: 11px 23px 9px 25px;
            }

            QGraphicsView {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f9fafb,
                    stop:0.5 #f3f4f6,
                    stop:1 #f9fafb
                );
                border: none;
            }
        """)

    def show_shortcuts(self):
        text = (
            "⌘ <b>Горячие клавиши:</b><br><br>"
            "▸ <b>Ctrl+N</b> — новый снимок<br>"
            "▸ <b>Ctrl+Shift+N</b> — коллаж<br>"
            "▸ <b>Ctrl+K</b> — история<br>"
            "▸ <b>Ctrl+C</b> — копировать<br>"
            "▸ <b>Ctrl+S</b> — сохранить<br>"
            "▸ <b>Ctrl+Z</b> — отмена<br>"
            "▸ <b>Ctrl+Y</b> — повтор<br>"
            "▸ <b>Delete</b> — удалить<br>"
            "▸ <b>Ctrl+Plus/Minus</b> — масштаб"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("⌘ Горячие клавиши")
        msg.setTextFormat(Qt.RichText)
        msg.setText(text)
        msg.setIcon(QMessageBox.Information)
        msg.exec()

    def show_about(self):
        text = (
            f"<h2 style='color: #2563eb;'>{APP_NAME}</h2>"
            f"<p><b>Версия:</b> {APP_VERSION}</p>"
            f"<p><b>Автор:</b> slipfaith</p>"
            f"<p style='color: #6b7280; font-size: 11px;'>Современный редактор скриншотов</p>"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("ⓘ О программе")
        msg.setTextFormat(Qt.RichText)
        msg.setText(text)
        msg.setIcon(QMessageBox.Information)
        msg.exec()

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
        result = self.logic.copy_to_clipboard()
        if result == "selection":
            message = "✓ Фрагмент скриншота скопирован"
        else:
            message = "✓ Скриншот скопирован"
        self.statusBar().showMessage(message, 2000)

    def save_image(self):
        name = self.logic.save_image(self)
        if name:
            self.statusBar().showMessage(f"✓ Сохранено: {name}", 3000)

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
                self.statusBar().showMessage("✕ Удалены выбранные элементы", 2000)
        elif event.matches(QKeySequence.Paste):
            if self._paste_from_clipboard():
                self.statusBar().showMessage("◉ Вставлено из буфера обмена", 2000)
            else:
                self.statusBar().showMessage("⚠️ В буфере нет изображения", 2000)
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
    def begin_capture_hide(self):
        self.setWindowState(self.windowState() | Qt.WindowMinimized)
        self.hide()
        QApplication.processEvents()

    def restore_from_capture(self):
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        QTimer.singleShot(0, lambda: (self.raise_(), self.activateWindow()))

    def load_base_screenshot(self, qimg: QImage, message: str = "◉ Новый скриншот", duration: int = 2000):
        self.canvas.set_base_image(qimg)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        if message:
            self.statusBar().showMessage(message, duration)

    def add_screenshot(self, collage: bool = False):
        try:
            from gui import OverlayManager
            self.begin_capture_hide()
            self.overlay_manager = OverlayManager(self.cfg)
            self.overlay_manager.captured.connect(lambda q: self._on_new_screenshot(q, collage))
            QTimer.singleShot(25, self.overlay_manager.start)
        except Exception as e:
            self.show()
            QMessageBox.critical(self, "Ошибка", f"Не удалось захватить скриншот: {e}")

    def new_screenshot(self):
        self.add_screenshot(collage=False)

    def _rounded_pixmap(self, qimg: QImage, radius: int = 16) -> QPixmap:
        pixmap = QPixmap(qimg.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        hints = QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        if hasattr(QPainter, "HighQualityAntialiasing"):
            hints |= QPainter.HighQualityAntialiasing
        painter.setRenderHints(hints)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, qimg.width(), qimg.height()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, QPixmap.fromImage(qimg))
        painter.end()
        return pixmap

    def _insert_screenshot_item(self, qimg: QImage, item_tag: str = "screenshot"):
        pixmap = self._rounded_pixmap(qimg)
        screenshot_item = QGraphicsPixmapItem(pixmap)
        screenshot_item.setTransformationMode(Qt.SmoothTransformation)
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        screenshot_item.setData(0, item_tag)
        self.canvas.scene.addItem(screenshot_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, screenshot_item))

        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        r = screenshot_item.boundingRect()
        screenshot_item.setPos(view_center.x() - r.width() / 2, view_center.y() - r.height() / 2)
        screenshot_item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        self.canvas._apply_lock_state()

    def _paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        images = images_from_mime(clipboard.mimeData())
        inserted = False
        for qimg in images:
            if not qimg.isNull():
                self._insert_screenshot_item(qimg)
                inserted = True
        return inserted

    def open_meme_library(self):
        self._meme_library_dialog.show()
        self._meme_library_dialog.raise_()
        self._meme_library_dialog.activateWindow()

    def _insert_meme_from_library(self, path: Path):
        qimg = QImage(str(path))
        if qimg.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить мем из библиотеки.")
            return
        self._insert_screenshot_item(qimg, item_tag="meme")
        self.statusBar().showMessage("◉ Мем добавлен на холст", 2500)

    def notify_meme_saved(self, path: Path):
        self.statusBar().showMessage(f"◉ Мем сохранён в библиотеку: {path.name}", 2500)
        self._meme_library_dialog.refresh_if_visible()

    def _on_new_screenshot(self, qimg: QImage, collage: bool):
        try:
            self.overlay_manager.close_all()
        except Exception:
            pass
        self.restore_from_capture()
        try:
            save_history(qimage_to_pil(qimg))
        except Exception:
            pass

        if collage:
            self._insert_screenshot_item(qimg)
            self.statusBar().showMessage(
                "◉ Новый скриншот добавлен (можно двигать и масштабировать)", 2500
            )
        else:
            self.load_base_screenshot(qimg)

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
                    f"◉ Добавлено из истории: {added}", 2500
                )

    def closeEvent(self, event):
        super().closeEvent(event)
