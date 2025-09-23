# -*- coding: utf-8 -*-
import io

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QInputDialog,
)

from logic import APP_NAME, APP_VERSION, qimage_to_pil, save_history, save_config
from editor.text_tools import TextManager
from editor.live_ocr import LiveTextManager
from editor.editor_logic import EditorLogic

from editor.undo_commands import AddCommand, RemoveCommand, ScaleCommand

from .ui.canvas import Canvas
from .ui.styles import main_window_style
from .ui.color_widgets import HexColorDialog
from .ui.toolbar_factory import create_tools_toolbar, create_actions_toolbar
from .ui.window_utils import size_to_image
from .ui.teams_dialog import TeamsSettingsDialog
from teams_integration import send_message_to_teams, TeamsSendError


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
        self.act_teams = actions['teams']
        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        self.shortcut_collage = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self.shortcut_collage.activated.connect(lambda: self.add_screenshot(collage=True))

        QTimer.singleShot(0, lambda q=qimg: size_to_image(self, q))

        self.statusBar().showMessage(
            "Готово | Ctrl+N: новый скриншот | Ctrl+Shift+N: коллаж | Ctrl+K: история | Ctrl+L: Live | Ctrl+Shift+T: Teams | Del: удалить | Ctrl +/-: масштаб",
            5000,
        )

        # Меню справки с горячими клавишами
        help_menu = self.menuBar().addMenu("Справка")
        act_shortcuts = help_menu.addAction("Горячие клавиши")
        act_shortcuts.triggered.connect(self.show_shortcuts)
        act_about = help_menu.addAction("О программе")
        act_about.triggered.connect(self.show_about)

    def show_shortcuts(self):
        text = (
            "Ctrl+N — новый снимок\n"
            "Ctrl+Shift+N — коллаж\n"
            "Ctrl+K — история\n"
            "Ctrl+L — Live Text\n"
            "Ctrl+Shift+T — отправить в Teams\n"
            "Ctrl+C — копировать\n"
            "Ctrl+S — сохранить\n"
            "Ctrl+Z — отмена\n"
            "Ctrl+Y — повтор\n"
            "Delete — удалить\n"
            "Ctrl+Plus/Minus — масштаб"
        )
        QMessageBox.information(self, "Горячие клавиши", text)

    def show_about(self):
        text = f"{APP_NAME}\nВерсия: {APP_VERSION}\nАвтор: slipfaith"
        QMessageBox.about(self, "О программе", text)

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
        if result == "text":
            message = "✅ Текст скопирован в буфер обмена"
        elif result == "selection":
            message = "✅ Фрагмент скриншота скопирован"
        else:
            message = "✅ Скриншот скопирован"
        self.statusBar().showMessage(message, 2000)

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

    def open_teams_settings(self) -> bool:
        dlg = TeamsSettingsDialog(self, self.cfg)
        if dlg.exec():
            self.cfg.update(dlg.values())
            save_config(self.cfg)
            self.statusBar().showMessage("🟣 Настройки Teams сохранены", 2500)
            return True
        return False

    def _ensure_teams_identity(self) -> bool:
        name = self.cfg.get("teams_user_name", "").strip()
        webhook = self.cfg.get("teams_webhook_url", "").strip()
        if name and webhook:
            return True
        return self.open_teams_settings()

    def send_to_teams(self):
        if not self._ensure_teams_identity():
            return

        default_text = ""
        try:
            if getattr(self, "live_manager", None):
                default_text = (self.live_manager.selected_text() or "").strip()
        except Exception:
            default_text = ""

        message_text, ok = QInputDialog.getMultiLineText(
            self,
            "Отправить в Microsoft Teams",
            "Сообщение:",
            default_text,
        )
        if not ok:
            return

        try:
            img = self.logic.export_image()
        except Exception as exc:
            QMessageBox.critical(self, "Microsoft Teams", f"Не удалось подготовить изображение: {exc}")
            return

        buffer = io.BytesIO()
        try:
            img.save(buffer, format="PNG")
        except Exception as exc:
            QMessageBox.critical(self, "Microsoft Teams", f"Не удалось сформировать PNG: {exc}")
            return

        webhook = self.cfg.get("teams_webhook_url", "").strip()
        user_name = self.cfg.get("teams_user_name", "").strip()
        user_email = self.cfg.get("teams_user_email", "").strip()

        try:
            send_message_to_teams(
                webhook,
                user_name=user_name,
                user_email=user_email,
                message=message_text,
                image_bytes=buffer.getvalue(),
            )
        except TeamsSendError as exc:
            QMessageBox.critical(self, "Microsoft Teams", f"Не удалось отправить сообщение: {exc}")
            return

        self.statusBar().showMessage("🟣 Сообщение отправлено в Microsoft Teams", 3000)

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

    def load_base_screenshot(self, qimg: QImage, message: str = "📸 Новый скриншот", duration: int = 2000):
        try:
            if getattr(self, "live_manager", None):
                self.live_manager.disable()
        except Exception:
            pass
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

    def _rounded_pixmap(self, qimg: QImage, radius: int = 12) -> QPixmap:
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

    def _insert_screenshot_item(self, qimg: QImage):
        pixmap = self._rounded_pixmap(qimg)
        screenshot_item = QGraphicsPixmapItem(pixmap)
        screenshot_item.setTransformationMode(Qt.SmoothTransformation)
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        screenshot_item.setData(0, "screenshot")
        self.canvas.scene.addItem(screenshot_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, screenshot_item))

        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        r = screenshot_item.boundingRect()
        screenshot_item.setPos(view_center.x() - r.width() / 2, view_center.y() - r.height() / 2)
        screenshot_item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        self.canvas._apply_lock_state()

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
                "📸 Новый скриншот добавлен (можно двигать и масштабировать)", 2500
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
