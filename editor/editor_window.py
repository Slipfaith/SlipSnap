# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Callable, Optional, List, Tuple, Type, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QAction,
    QImage,
    QPixmap,
    QPainter,
    QPainterPath,
    QKeySequence,
    QShortcut,
    QFont,
    QColor,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QApplication,
    QGraphicsItem,
    QGraphicsTextItem,
    QWidget,
    QToolButton,
)

from logic import APP_NAME, APP_VERSION, qimage_to_pil, save_history
from editor.text_tools import TextManager
from editor.editor_logic import EditorLogic
from editor.image_utils import images_from_mime

from editor.undo_commands import AddCommand, RemoveCommand, ScaleCommand

from .ui.canvas import Canvas
from .ui.high_quality_pixmap_item import HighQualityPixmapItem
from .ui.color_widgets import HexColorDialog
from .ui.toolbar_factory import create_tools_toolbar, create_actions_toolbar
from .ui.window_utils import size_to_image
from .ui.meme_library_dialog import MemesDialog
from icons import make_icon_series

from design_tokens import Metrics, Palette, Typography, editor_main_stylesheet

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from ocr import OcrEngine, OcrError, OcrUnavailableError, OcrSpan


class EditorWindow(QMainWindow):
    """Main editor window with modern light design."""

    def __init__(self, qimg: QImage, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap — Редактор")

        self.setMinimumSize(Metrics.MAIN_WINDOW_MIN_WIDTH, Metrics.MAIN_WINDOW_MIN_HEIGHT)

        self.canvas = Canvas(qimg)
        self.text_manager = TextManager(self.canvas)
        self.canvas.set_text_manager(self.text_manager)
        self.logic = EditorLogic(self.canvas)
        self._ocr_engine = None  # type: Optional["OcrEngine"]
        self._ocr_error_cls = None  # type: Optional[Type["OcrError"]]
        self._ocr_unavailable_cls = None  # type: Optional[Type["OcrUnavailableError"]]
        self._ocr_import_error = None  # type: Optional[ImportError]

        self.setCentralWidget(self.canvas)
        self._apply_modern_stylesheet()
        self.canvas.imageDropped.connect(self._insert_screenshot_item)

        self._start_series_handler: Optional[Callable[[Optional[QWidget]], bool]] = None
        self._series_state_getter: Optional[Callable[[], bool]] = None
        self._series_action: Optional[QAction] = None
        self._series_button: Optional[QToolButton] = None

        self._tool_buttons = create_tools_toolbar(self, self.canvas)
        self.color_btn, actions, action_buttons = create_actions_toolbar(self, self.canvas)
        self._series_action = actions.get("series")
        self._series_button = action_buttons.get("series")
        if self._series_action is not None:
            self._series_action.setIcon(make_icon_series())
        if self._series_button is not None:
            self._series_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self._series_button.setText("🎞")
            self._series_button.setToolTip("Серия скриншотов")
        self._update_series_button_state()
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

        self._memes_dialog = MemesDialog(self)
        self._memes_dialog.memeSelected.connect(self._insert_meme_from_dialog)

        # Меню справки с горячими клавишами
        help_menu = self.menuBar().addMenu("Справка")
        act_shortcuts = help_menu.addAction("⌘ Горячие клавиши")
        act_shortcuts.triggered.connect(self.show_shortcuts)
        act_about = help_menu.addAction("ⓘ О программе")
        act_about.triggered.connect(self.show_about)

        self._recognized_items: List[QGraphicsTextItem] = []

    # ---- OCR -------------------------------------------------------
    def _target_pixmap_items(self) -> List[HighQualityPixmapItem]:
        items: List[HighQualityPixmapItem] = []
        base_item = getattr(self.canvas, "pixmap_item", None)
        if isinstance(base_item, HighQualityPixmapItem) and not base_item.pixmap().isNull():
            items.append(base_item)

        for item in self.canvas.scene.items():
            if isinstance(item, HighQualityPixmapItem) and item is not base_item and not item.pixmap().isNull():
                items.append(item)
        return items

    def _clear_ocr_layer(self) -> None:
        for text_item in self._recognized_items:
            scene = text_item.scene()
            if scene is not None:
                scene.removeItem(text_item)
        self._recognized_items.clear()

    def _create_text_overlay(self, parent: HighQualityPixmapItem, span: "OcrSpan") -> QGraphicsTextItem:
        overlay = QGraphicsTextItem(span.text, parent)
        overlay.setData(0, "ocr_text")
        overlay.setDefaultTextColor(QColor(Palette.TEXT_PRIMARY))
        overlay.setOpacity(0.02)
        overlay.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        overlay.setFlag(QGraphicsItem.ItemIsSelectable, False)
        overlay.setFlag(QGraphicsItem.ItemIsMovable, False)
        overlay.setFlag(QGraphicsItem.ItemIsFocusable, True)
        overlay.setCursor(Qt.IBeamCursor)
        overlay.setPos(span.bbox.left(), span.bbox.top())
        overlay.setTextWidth(span.bbox.width())
        overlay.setZValue(parent.zValue() + 0.1)
        font = QFont(Typography.UI_FAMILY)
        point_size = max(8.0, min(36.0, span.bbox.height() * 0.75))
        font.setPointSizeF(point_size)
        overlay.setFont(font)
        overlay.document().setDocumentMargin(0)
        return overlay

    def _ensure_ocr_engine(self) -> Tuple["OcrEngine", Type["OcrError"], Type["OcrUnavailableError"]]:
        if self._ocr_import_error is not None:
            raise self._ocr_import_error

        if (
            self._ocr_engine is not None
            and self._ocr_error_cls is not None
            and self._ocr_unavailable_cls is not None
        ):
            return self._ocr_engine, self._ocr_error_cls, self._ocr_unavailable_cls

        try:
            from ocr import OcrEngine, OcrError, OcrUnavailableError
        except ImportError as exc:  # pragma: no cover - optional dependency
            self._ocr_import_error = exc
            raise

        self._ocr_engine = OcrEngine()
        self._ocr_error_cls = OcrError
        self._ocr_unavailable_cls = OcrUnavailableError
        self._ocr_import_error = None
        return self._ocr_engine, self._ocr_error_cls, self._ocr_unavailable_cls

    def _show_ocr_dependency_error(self, exc: ImportError) -> None:
        module_name = getattr(exc, "name", None)
        if module_name:
            detail = f"Модуль `{module_name}` не найден."
        else:
            detail = "Не удалось загрузить поддержку OCR."
        message = (
            f"{detail}\n"
            "Установите дополнительные зависимости OCR, например `pip install pytesseract`."
        )
        QMessageBox.warning(self, "OCR недоступен", message)

    def recognize_text_layer(self) -> None:
        pixmap_items = self._target_pixmap_items()
        if not pixmap_items:
            QMessageBox.information(self, "SlipSnap", "Нет изображений для распознавания текста.")
            return

        self._clear_ocr_layer()

        total_lines = 0

        try:
            engine, ocr_error_cls, ocr_unavailable_cls = self._ensure_ocr_engine()
        except ImportError as exc:
            self._show_ocr_dependency_error(exc)
            return

        try:
            for pixmap_item in pixmap_items:
                spans = engine.recognize(pixmap_item.pixmap().toImage())
                for span in spans:
                    overlay = self._create_text_overlay(pixmap_item, span)
                    self._recognized_items.append(overlay)
                total_lines += len(spans)
        except ocr_unavailable_cls as exc:
            QMessageBox.warning(self, "OCR недоступен", str(exc))
            return
        except ocr_error_cls as exc:
            QMessageBox.warning(self, "Ошибка OCR", f"Не удалось распознать текст:\n{exc}")
            return

        if total_lines:
            self.statusBar().showMessage(f"◉ OCR: найдено строк {total_lines}", 4000)
        else:
            self.statusBar().showMessage("⚠️ OCR: текст не найден", 4000)

    # ---- series controls ------------------------------------------
    def set_series_controls(
        self,
        start_handler: Callable[[Optional[QWidget]], bool],
        state_getter: Callable[[], bool],
    ) -> None:
        self._start_series_handler = start_handler
        self._series_state_getter = state_getter
        self.update_series_state()

    def request_series_capture(self) -> None:
        if not self._start_series_handler:
            QMessageBox.information(
                self,
                "SlipSnap",
                "Настройка серии сейчас недоступна.",
            )
            return

        started = self._start_series_handler(self)
        if started:
            self.statusBar().showMessage("◉ Серия активирована", 3000)
        self.update_series_state()

    def update_series_state(self) -> None:
        self._update_series_button_state()

    def _update_series_button_state(self) -> None:
        if self._series_button is None:
            return
        active = False
        if self._series_state_getter is not None:
            try:
                active = bool(self._series_state_getter())
            except Exception:
                active = False
        tooltip = "Начать серию скриншотов"
        if active:
            tooltip = (
                "Серия активна — используйте Esc в режиме съёмки, чтобы завершить её."
            )
        self._series_button.setToolTip(tooltip)

    def _apply_modern_stylesheet(self):
        """Apply modern light theme with clean design."""
        self.setStyleSheet(editor_main_stylesheet())

    def show_shortcuts(self):
        shortcuts = (
            "SlipSnap — горячие клавиши\n\n"
            "Ctrl+N — новый снимок\n"
            "Ctrl+Shift+N — коллаж\n"
            "Ctrl+K — история\n"
            "Ctrl+C — копировать\n"
            "Ctrl+S — сохранить\n"
            "Ctrl+Z — отмена\n"
            "Ctrl+X — вернуть отменённое\n"
            "Delete — удалить\n"
            "Ctrl+Plus/Minus — масштаб"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("SlipSnap · Горячие клавиши")
        msg.setTextFormat(Qt.PlainText)
        msg.setIcon(QMessageBox.NoIcon)
        msg.setText(shortcuts)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def show_about(self):
        text = (
            f"{APP_NAME} {APP_VERSION}\n"
            "Современный редактор скриншотов\n"
            "Автор: slipfaith"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("SlipSnap · О программе")
        msg.setTextFormat(Qt.PlainText)
        msg.setIcon(QMessageBox.NoIcon)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
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
            selected_items = list(self.canvas.scene.selectedItems())
            for item in selected_items:
                self.canvas.scene.removeItem(item)
                self.canvas.handle_item_removed(item)
                self.canvas.undo_stack.push(
                    RemoveCommand(
                        self.canvas.scene,
                        item,
                        on_removed=self.canvas.handle_item_removed,
                        on_restored=self.canvas.handle_item_restored,
                    )
                )
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
        self._clear_ocr_layer()
        self.canvas.set_base_image(qimg)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        if message:
            self.statusBar().showMessage(message, duration)
        QTimer.singleShot(0, lambda q=qimg: size_to_image(self, q))

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
        self._clear_ocr_layer()
        pixmap = self._rounded_pixmap(qimg)
        screenshot_item = HighQualityPixmapItem(pixmap.toImage())
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
        self.canvas.update_scene_rect()

    def _paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        images = images_from_mime(clipboard.mimeData())
        inserted = False
        for qimg in images:
            if not qimg.isNull():
                self._insert_screenshot_item(qimg)
                inserted = True
        return inserted

    def open_memes_dialog(self):
        self._memes_dialog.show()
        self._memes_dialog.raise_()
        self._memes_dialog.activateWindow()

    def _insert_meme_from_dialog(self, path: Path):
        qimg = QImage(str(path))
        if qimg.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить мем.")
            return
        self._insert_screenshot_item(qimg, item_tag="meme")
        self.statusBar().showMessage("◉ Мем добавлен на холст", 2500)

    def notify_meme_saved(self, path: Path):
        self.statusBar().showMessage(f"◉ Мем сохранён: {path.name}", 2500)
        self._memes_dialog.refresh_if_visible()

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
