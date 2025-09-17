# -*- coding: utf-8 -*-
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Set

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QFileDialog,
    QMenu,
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
        self.color_btn, actions, action_buttons = create_actions_toolbar(self, self.canvas)
        self.act_live = actions['live']
        self.btn_live = action_buttons.get('live')
        self._live_button_default_style = self.btn_live.styleSheet() if self.btn_live else ""
        self.act_new = actions['new']
        self.act_collage = actions['collage']
        if hasattr(self, 'act_collage'):
            self._update_collage_enabled()

        self.shortcut_collage = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self.shortcut_collage.activated.connect(lambda: self.add_screenshot(collage=True))

        self._live_ocr_available = True
        if self.btn_live is not None:
            self.btn_live.setContextMenuPolicy(Qt.CustomContextMenu)
            self.btn_live.customContextMenuRequested.connect(self._show_live_context_menu)
        self._init_live_ocr()

        QTimer.singleShot(0, lambda q=qimg: size_to_image(self, q))

        self.statusBar().showMessage(
            "Готово | Ctrl+N: новый скриншот | Ctrl+Shift+N: коллаж | Ctrl+K: история | Ctrl+L: Live | Del: удалить | Ctrl +/-: масштаб",
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

    # ---- live ocr helpers ----
    def _init_live_ocr(self) -> None:
        enabled = self.cfg.get("live_ocr_enabled", True)
        if not enabled:
            self._set_live_ocr_available(False)
            return
        if self._ensure_tesseract_path(interactive=False):
            self._set_live_ocr_available(True)
            return
        if self._ensure_tesseract_path(interactive=True):
            self._set_live_ocr_available(True)
        else:
            self._disable_live_ocr(notify=True)

    def _set_live_ocr_available(self, available: bool) -> None:
        self._live_ocr_available = available
        if self.btn_live is None:
            return
        if available:
            self.btn_live.setStyleSheet(self._live_button_default_style)
            self.btn_live.setCursor(Qt.PointingHandCursor)
            self.btn_live.setToolTip("Live Text (Ctrl+L)")
        else:
            parts = [self._live_button_default_style] if self._live_button_default_style else []
            parts.append("color: rgba(120, 120, 120, 180);")
            self.btn_live.setStyleSheet(" ".join(p for p in parts if p))
            self.btn_live.setCursor(Qt.ArrowCursor)
            self.btn_live.setToolTip("Live Text недоступен. Правый клик — указать tesseract.exe")

    def _current_tesseract_exists(self) -> bool:
        path = self.cfg.get("tesseract_path")
        if not path:
            return False
        try:
            candidate = Path(path)
        except (TypeError, ValueError):
            return False
        return candidate.exists() and candidate.is_file()

    def _ensure_tesseract_path(self, interactive: bool, manual: bool = False) -> bool:
        candidate = self._locate_tesseract_existing()
        if candidate:
            self._apply_tesseract_path(candidate)
            return True
        if not interactive:
            return False
        if not manual:
            answer = QMessageBox.question(
                self,
                "Tesseract OCR",
                "SlipSnap не нашёл установленный Tesseract OCR. Указать путь к tesseract.exe?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return False
        chosen = self._ask_user_for_tesseract()
        if chosen:
            self._apply_tesseract_path(chosen)
            return True
        return False

    def _locate_tesseract_existing(self) -> Optional[Path]:
        for candidate in self._tesseract_candidates():
            if LiveTextManager.validate_tesseract_path(candidate):
                return candidate
        return None

    def _tesseract_candidates(self) -> List[Path]:
        exe_name = "tesseract.exe" if os.name == "nt" else "tesseract"
        candidates: List[Path] = []
        seen: Set[str] = set()

        def add(path_like) -> None:
            if not path_like:
                return
            try:
                p = Path(path_like)
            except (TypeError, ValueError):
                return
            try:
                resolved = p.resolve()
            except Exception:
                resolved = p
            key = str(resolved)
            if key in seen:
                return
            seen.add(key)
            candidates.append(resolved)

        add(self.cfg.get("tesseract_path"))

        for name in ("tesseract.exe", "tesseract"):
            env_path = shutil.which(name)
            if env_path:
                add(env_path)

        for base in self._candidate_directories():
            add(base / exe_name)
            add(base / "tesseract" / exe_name)

        if os.name == "nt":
            for env_var in ("PROGRAMFILES", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                base_dir = os.environ.get(env_var)
                if base_dir:
                    add(Path(base_dir) / "Tesseract-OCR" / exe_name)

        return [p for p in candidates if p.exists() and p.is_file()]

    def _candidate_directories(self) -> List[Path]:
        dirs: List[Path] = []
        try:
            dirs.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
        try:
            dirs.append(Path(sys.argv[0]).resolve().parent)
        except Exception:
            pass
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            try:
                dirs.append(Path(bundle))
            except Exception:
                pass
        module_dir = Path(__file__).resolve().parent
        dirs.extend([module_dir, module_dir.parent, Path.cwd()])

        unique: List[Path] = []
        seen: Set[str] = set()
        for d in dirs:
            try:
                resolved = d.resolve()
            except Exception:
                resolved = d
            if not resolved.exists():
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            unique.append(resolved)
        return unique

    def _apply_tesseract_path(self, path: Path) -> None:
        self.cfg["tesseract_path"] = str(path)
        self.cfg["live_ocr_enabled"] = True
        save_config(self.cfg)
        self.live_manager.set_tesseract_cmd(str(path))

    def _ask_user_for_tesseract(self) -> Optional[Path]:
        exe_name = "tesseract.exe" if os.name == "nt" else "tesseract"
        while True:
            directory = QFileDialog.getExistingDirectory(self, "Укажите папку с Tesseract OCR")
            if not directory:
                return None
            candidate = Path(directory) / exe_name
            if not candidate.exists():
                retry = QMessageBox.question(
                    self,
                    "Tesseract OCR",
                    f"В папке «{directory}» не найден {exe_name}. Повторить поиск?",
                    QMessageBox.Retry | QMessageBox.Cancel,
                    QMessageBox.Retry,
                )
                if retry == QMessageBox.Retry:
                    continue
                return None
            if LiveTextManager.validate_tesseract_path(candidate):
                return candidate
            retry = QMessageBox.question(
                self,
                "Tesseract OCR",
                f"Не удалось запустить {exe_name} по указанному пути. Повторить поиск?",
                QMessageBox.Retry | QMessageBox.Cancel,
                QMessageBox.Retry,
            )
            if retry != QMessageBox.Retry:
                return None

    def _show_live_context_menu(self, pos) -> None:
        if self.btn_live is None:
            return
        menu = QMenu(self.btn_live)
        find_action = menu.addAction("Найти tesseract.exe…")
        chosen = menu.exec(self.btn_live.mapToGlobal(pos))
        if chosen == find_action:
            if self._ensure_tesseract_path(interactive=True, manual=True):
                self._set_live_ocr_available(True)
                self.statusBar().showMessage("🔍 Tesseract OCR найден", 3000)
            elif not self._current_tesseract_exists():
                self._disable_live_ocr()

    def _disable_live_ocr(self, notify: bool = False) -> None:
        self.cfg["live_ocr_enabled"] = False
        self.cfg["tesseract_path"] = ""
        save_config(self.cfg)
        try:
            self.live_manager.disable()
        except Exception:
            pass
        try:
            self.live_manager.set_tesseract_cmd(None)
        except Exception:
            pass
        self._set_live_ocr_available(False)
        if notify:
            QMessageBox.information(
                self,
                "Tesseract OCR",
                "Live Text отключён. Правый клик по иконке позволит указать путь к tesseract.exe.",
            )

    def _handle_live_text_error(self) -> None:
        error = getattr(self.live_manager, "last_error", None)
        code = message = None
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
        if code == "not_found":
            QMessageBox.warning(
                self,
                "Tesseract OCR",
                "Не удалось найти tesseract.exe. Укажите путь вручную.",
            )
            if self._ensure_tesseract_path(interactive=True, manual=True):
                self._set_live_ocr_available(True)
                retry = self.logic.toggle_live_text()
                if retry == "enabled":
                    self.statusBar().showMessage("🔍 Live Text — включено", 3500)
                    return
                if retry == "disabled":
                    self.statusBar().showMessage("🔍 Live Text — выключено", 2000)
                    return
                next_error = getattr(self.live_manager, "last_error", None)
                extra = ""
                if isinstance(next_error, dict):
                    extra = next_error.get("message", "") or ""
                text = "Не удалось включить Live Text."
                if extra:
                    text += f"\n{extra}"
                QMessageBox.warning(self, "SlipSnap", text)
                return
            self._disable_live_ocr()
            self.statusBar().showMessage("🔍 Live Text — выключено", 3000)
        else:
            text = "Не удалось включить Live Text."
            if message:
                text += f"\n{message}"
            QMessageBox.warning(self, "SlipSnap", text)

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
        if not getattr(self, "_live_ocr_available", True):
            self.statusBar().showMessage(
                "🔍 Live Text недоступен — правый клик чтобы указать путь к tesseract.exe",
                4000,
            )
            return
        if not self._current_tesseract_exists():
            if not self._ensure_tesseract_path(interactive=True, manual=True):
                self._disable_live_ocr()
                self.statusBar().showMessage("🔍 Live Text — выключено", 3000)
                return
            self._set_live_ocr_available(True)
        result = self.logic.toggle_live_text()
        if result == "enabled":
            self.statusBar().showMessage("🔍 Live Text — включено", 3500)
        elif result == "disabled":
            self.statusBar().showMessage("🔍 Live Text — выключено", 2000)
        else:
            self._handle_live_text_error()

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
