# -*- coding: utf-8 -*-

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QRectF, Signal, QThread, QMimeData, QCoreApplication
from PySide6.QtGui import QAction, QImage, QPixmap, QPainter, QPainterPath, QKeySequence, QShortcut, QColor, QMovie
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from logic import qimage_to_pil, save_history, save_config
from editor.text_tools import TextManager
from editor.ocr_overlay import OcrCapture
from editor.editor_logic import EditorLogic
from editor.image_utils import images_from_mime, gif_paths_from_mime, gif_bytes_from_mime
from ocr import (
    OcrError,
    OcrResult,
    OcrSettings,
    get_language_display_name,
    run_ocr,
    get_available_languages,
    download_tesseract_languages,
    LANGUAGE_DISPLAY_NAMES,
)

from editor.undo_commands import AddCommand, RemoveCommand, ScaleCommand

from .ui.canvas import Canvas
from .ui.high_quality_pixmap_item import HighQualityPixmapItem
from .ui.color_widgets import HexColorDialog
from .ui.toolbar_factory import create_tools_toolbar, create_actions_toolbar
from .ui.styles import ModernColors
from .ui.window_utils import size_to_image
from .ui.meme_library_dialog import MemesDialog
from icons import make_icon_series, make_icon_video

from design_tokens import Metrics, editor_main_stylesheet

logger = logging.getLogger(__name__)


class _AnimatedGifItem(QGraphicsPixmapItem):
    """Scene item that renders an animated GIF using QMovie frames."""

    def __init__(self, gif_path: Path):
        super().__init__()
        self._gif_path = Path(gif_path)
        self._movie = QMovie(str(self._gif_path))
        if not self._movie.isValid():
            raise ValueError(f"Не удалось открыть GIF: {self._gif_path}")
        self._movie.frameChanged.connect(self._on_frame_changed)
        self._movie.start()
        if self._movie.currentPixmap().isNull():
            self._movie.jumpToFrame(0)
        self._on_frame_changed(0)
        self.setTransformationMode(Qt.SmoothTransformation)

    def _on_frame_changed(self, _frame_no: int) -> None:
        pix = self._movie.currentPixmap()
        if not pix.isNull():
            self.setPixmap(pix)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSceneHasChanged:
            self._movie.setPaused(value is None)
        return super().itemChange(change, value)

    def source_path(self) -> Path:
        return self._gif_path


class _OcrWorker(QThread):
    finished = Signal(object, object)

    def __init__(self, capture: OcrCapture, settings: OcrSettings, language_hint: str):
        super().__init__()
        self.capture = capture
        self.settings = settings
        self.language_hint = language_hint

    def run(self):
        result = None
        error = None
        try:
            result = run_ocr(self.capture.image.copy(), self.settings, language_hint=self.language_hint)
        except Exception as exc:  # noqa: BLE001
            error = exc
        self.finished.emit(result, error)


class _LanguagePickerDialog(QDialog):
    """Modern dialog for selecting OCR languages."""

    def __init__(self, parent: QWidget, available: list[str], default_lang: str, preferred: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Распознать текст")
        self.setFixedWidth(360)
        self._priority_codes = ["rus", "eng", "chi_sim"]
        self._available = sorted(set(available))
        self._selected_languages: set[str] = set()
        self._build_ui(default_lang, preferred)

    def _build_ui(self, default_lang: str, preferred: list[str]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Языки OCR")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        self.auto_checkbox = QCheckBox("Определять язык автоматически")
        self.auto_checkbox.setChecked(not default_lang or default_lang.lower() == "auto")
        self.auto_checkbox.toggled.connect(self._sync_enabled_state)
        layout.addWidget(self.auto_checkbox)

        priority_block = QFrame(self)
        priority_block.setFrameShape(QFrame.StyledPanel)
        priority_block.setStyleSheet("QFrame { border: 1px solid #d0d7de; border-radius: 10px; }")
        priority_layout = QVBoxLayout(priority_block)
        priority_layout.setContentsMargins(10, 8, 10, 8)
        priority_layout.setSpacing(8)

        priority_title = QLabel("Быстрый выбор")
        priority_title.setStyleSheet("font-weight: 600;")
        priority_layout.addWidget(priority_title)

        self._priority_checks: dict[str, QCheckBox] = {}
        row = QHBoxLayout()
        row.setSpacing(8)
        for code in self._priority_codes:
            label = get_language_display_name(code) or code
            cb = QCheckBox(label)
            cb.toggled.connect(lambda checked, lang=code: self._toggle_language(lang, checked))
            row.addWidget(cb)
            self._priority_checks[code] = cb
        row.addStretch(1)
        priority_layout.addLayout(row)

        search_label = QLabel("Найти другой язык")
        search_label.setStyleSheet("font-weight: 600;")
        priority_layout.addWidget(search_label)

        self.search_edit = QLineEdit(priority_block)
        self.search_edit.setPlaceholderText("Поиск по названию или коду")
        self.search_edit.textChanged.connect(self._filter_languages)
        self.search_edit.returnPressed.connect(self._add_custom_language)
        priority_layout.addWidget(self.search_edit)

        self.list_widget = QListWidget(priority_block)
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setMinimumHeight(110)
        priority_layout.addWidget(self.list_widget)

        layout.addWidget(priority_block)

        available_text = ", ".join(self._available) if self._available else "нет установленных языков"
        info = QLabel(f"Установлено: {available_text}")
        info.setWordWrap(True)
        info.setStyleSheet("color: #6e7781;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        selected_codes: list[str] = []
        if default_lang and default_lang.lower() != "auto":
            selected_codes = [code.strip() for code in default_lang.split("+") if code.strip()]
        if not selected_codes:
            selected_codes = preferred
        self._selected_languages = set(selected_codes)

        for code, checkbox in self._priority_checks.items():
            checkbox.setChecked(code in self._selected_languages)

        self._filter_languages(self.search_edit.text())
        self._sync_enabled_state(self.auto_checkbox.isChecked())

    def _filter_languages(self, query: str) -> None:
        try:
            self.list_widget.itemChanged.disconnect(self._on_list_item_changed)
        except TypeError:
            pass
        self.list_widget.clear()
        normalized_query = query.strip().lower()
        other_languages = [code for code in self._available if code not in self._priority_codes]
        for code in other_languages:
            display = get_language_display_name(code)
            if normalized_query and normalized_query not in code.lower() and (display and normalized_query not in display.lower()):
                continue
            item = QListWidgetItem(display or code)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in self._selected_languages else Qt.Unchecked)
            self.list_widget.addItem(item)
        if self.list_widget.count() == 0:
            placeholder = QListWidgetItem("Нет совпадений")
            placeholder.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in self._selected_languages else Qt.Unchecked)

        self.list_widget.itemChanged.connect(self._on_list_item_changed)

    def _on_list_item_changed(self, item: QListWidgetItem) -> None:
        code = item.data(Qt.UserRole)
        if not code:
            return
        self._toggle_language(code, item.checkState() == Qt.Checked, refresh_list=False)

    def _add_custom_language(self) -> None:
        text = self.search_edit.text().strip()
        if not text:
            return
        code = text
        if code not in self._available:
            self._available.append(code)
            self._available.sort()
        self._toggle_language(code, True)
        self.search_edit.selectAll()

    def _toggle_language(self, language: str, checked: bool, refresh_list: bool = True) -> None:
        if checked:
            self._selected_languages.add(language)
        else:
            self._selected_languages.discard(language)
        if language in self._priority_checks:
            checkbox = self._priority_checks.get(language)
            if checkbox and checkbox.isChecked() != checked:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        if refresh_list:
            self._filter_languages(self.search_edit.text())

    def _sync_enabled_state(self, auto_enabled: bool) -> None:
        enabled = not auto_enabled
        for checkbox in self._priority_checks.values():
            checkbox.setEnabled(enabled)
        self.search_edit.setEnabled(enabled)
        self.list_widget.setEnabled(enabled)

    def selected_language(self) -> str:
        if self.auto_checkbox.isChecked():
            return "auto"

        if not self._selected_languages:
            return "eng"

        ordered = [code for code in self._priority_codes if code in self._selected_languages]
        ordered.extend(sorted(lang for lang in self._selected_languages if lang not in self._priority_codes))
        return "+".join(ordered)


class _OcrLanguageDownloadDialog(QDialog):
    def __init__(self, parent: QWidget, available: list[str], known_languages: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Скачать языки OCR")
        self.setFixedWidth(380)
        self._available = set(available)
        self._known = sorted(set(known_languages) | set(available))
        self._selected_languages: set[str] = set()
        self._list_item_connected = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Выберите языки для скачивания")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        info_text = "Установлено: " + (", ".join(sorted(self._available)) if self._available else "нет")
        info = QLabel(info_text)
        info.setWordWrap(True)
        info.setStyleSheet("color: #6e7781;")
        layout.addWidget(info)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Поиск по названию или коду")
        self.search_edit.textChanged.connect(self._filter_languages)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setMinimumHeight(180)
        layout.addWidget(self.list_widget)

        add_row = QHBoxLayout()
        self.custom_edit = QLineEdit(self)
        self.custom_edit.setPlaceholderText("Добавить код вручную (например: ukr)")
        add_btn = QToolButton(self)
        add_btn.setText("Добавить")
        add_btn.clicked.connect(self._add_custom_language)
        add_row.addWidget(self.custom_edit)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.summary = QLabel("Выбрано: 0")
        self.summary.setStyleSheet("color: #6e7781;")
        layout.addWidget(self.summary)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._filter_languages("")

    def _filter_languages(self, query: str) -> None:
        if self._list_item_connected:
            self.list_widget.itemChanged.disconnect(self._on_list_item_changed)
            self._list_item_connected = False
        self.list_widget.clear()
        normalized_query = query.strip().lower()
        for code in self._known:
            display = get_language_display_name(code) or code
            if normalized_query and normalized_query not in code.lower() and normalized_query not in display.lower():
                continue
            label = f"{display} ({code})"
            if code in self._available:
                label += " ✓"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in self._selected_languages else Qt.Unchecked)
            if code in self._available:
                item.setForeground(QColor("#6e7781"))
            self.list_widget.addItem(item)
        if self.list_widget.count() == 0:
            placeholder = QListWidgetItem("Нет совпадений")
            placeholder.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)
        self.list_widget.itemChanged.connect(self._on_list_item_changed)
        self._list_item_connected = True
        self._update_summary()

    def _on_list_item_changed(self, item: QListWidgetItem) -> None:
        code = item.data(Qt.UserRole)
        if not code:
            return
        if item.checkState() == Qt.Checked:
            self._selected_languages.add(code)
        else:
            self._selected_languages.discard(code)
        self._update_summary()

    def _add_custom_language(self) -> None:
        text = self.custom_edit.text().strip()
        if not text:
            return
        code = text
        if code not in self._known:
            self._known.append(code)
            self._known.sort()
        self._selected_languages.add(code)
        self.custom_edit.clear()
        self._filter_languages(self.search_edit.text())

    def _update_summary(self) -> None:
        self.summary.setText(f"Выбрано: {len(self._selected_languages)}")

    def selected_languages(self) -> list[str]:
        return sorted(self._selected_languages)


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
        self.logic = EditorLogic(self.canvas, self.cfg)
        self.ocr_settings = OcrSettings.from_config(self.cfg)
        self._last_ocr_capture: Optional[OcrCapture] = None
        self._last_ocr_language_hint: str = ""
        self._ocr_worker: Optional[_OcrWorker] = None
        self._ocr_toast: Optional[QWidget] = None
        self._ocr_toast_timer = QTimer(self)
        self._ocr_toast_timer.setSingleShot(True)
        self._ocr_toast_timer.timeout.connect(self._clear_ocr_toast)
        self._ocr_menu: Optional[QMenu] = None
        self._ocr_button: Optional[QToolButton] = None

        self.setCentralWidget(self.canvas)
        self._apply_modern_stylesheet()
        self.canvas.imageDropped.connect(self._insert_screenshot_item)

        self._start_series_handler: Optional[Callable[[Optional[QWidget]], bool]] = None
        self._series_state_getter: Optional[Callable[[], bool]] = None
        self._series_action: Optional[QAction] = None
        self._series_button: Optional[QToolButton] = None
        self._start_video_handler: Optional[Callable[[Optional[QWidget]], bool]] = None
        self._video_action: Optional[QAction] = None
        self._video_button: Optional[QToolButton] = None
        self._clipboard_temp_dirs: list[Path] = []
        self._share_worker: Optional[QThread] = None
        self._share_temp_file: Optional[Path] = None

        self._tool_buttons = create_tools_toolbar(self, self.canvas)
        self.color_btn, actions, action_buttons = create_actions_toolbar(self, self.canvas)
        self._series_action = actions.get("series")
        self._series_button = action_buttons.get("series")
        self._video_action = actions.get("video")
        self._video_button = action_buttons.get("video")
        self._ocr_button = action_buttons.get("ocr")
        if self._ocr_button is not None:
            self._setup_ocr_button(self._ocr_button)
        if self._series_action is not None:
            self._series_action.setIcon(make_icon_series())
        if self._video_action is not None:
            self._video_action.setIcon(make_icon_video())
        if self._series_button is not None:
            self._series_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self._series_button.setText("🎞")
            self._series_button.setToolTip("Серия скриншотов")
        if self._video_button is not None:
            self._video_button.setToolTip("Записать видео")
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

        self._memes_dialog = MemesDialog(self, cfg=self.cfg)
        self._memes_dialog.memeSelected.connect(self._insert_meme_from_dialog)

        # Меню справки с горячими клавишами
        help_menu = self.menuBar().addMenu("Справка")
        act_shortcuts = help_menu.addAction("⌘ Горячие клавиши")
        act_shortcuts.triggered.connect(self.show_shortcuts)
        act_about = help_menu.addAction("ⓘ О программе")
        act_about.triggered.connect(self.show_about)

    # ---- series controls ------------------------------------------
    def set_series_controls(
        self,
        start_handler: Callable[[Optional[QWidget]], bool],
        state_getter: Callable[[], bool],
    ) -> None:
        self._start_series_handler = start_handler
        self._series_state_getter = state_getter
        self.update_series_state()

    def set_video_capture_controls(
        self,
        start_handler: Callable[[Optional[QWidget]], bool],
    ) -> None:
        self._start_video_handler = start_handler

    def request_video_capture(self) -> None:
        if not self._start_video_handler:
            QMessageBox.information(
                self,
                "SlipSnap",
                "Запуск записи видео сейчас недоступен.",
            )
            return
        started = self._start_video_handler(self)
        if started:
            self.statusBar().showMessage("● Запись видео запущена", 3000)

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
        capture_hotkey = str(self.cfg.get("capture_hotkey", "Ctrl+Alt+S")).strip() or "Ctrl+Alt+S"
        video_hotkey = str(self.cfg.get("video_hotkey", "Ctrl+Alt+V")).strip() or "Ctrl+Alt+V"
        shortcuts = (
            "SlipSnap — горячие клавиши\n\n"
            f"{capture_hotkey} — снимок области (глобально)\n"
            f"{video_hotkey} — запись видео (глобально)\n\n"
            "Ctrl+N — новый снимок\n"
            "Ctrl+Shift+N — коллаж\n"
            "Ctrl+K — история\n"
            "Ctrl+A — выделить всё\n"
            "Ctrl+C — копировать\n"
            "Ctrl+S — сохранить\n"
            "Ctrl+Z — отмена\n"
            "Ctrl+X — вернуть отменённое\n"
            "Delete — удалить\n"
            "G — лупа\n"
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
        app_name = QCoreApplication.applicationName() or "SlipSnap"
        app_version = str(QCoreApplication.applicationVersion() or "").strip()
        header = f"{app_name} {app_version}".strip()
        app = QCoreApplication.instance()
        description = "Современный редактор скриншотов"
        author = "slipfaith"
        if app is not None:
            app_description = app.property("app_description")
            if isinstance(app_description, str) and app_description.strip():
                description = app_description.strip()
            app_author = app.property("app_author")
            if isinstance(app_author, str) and app_author.strip():
                author = app_author.strip()
        text = (
            f"{header}\n"
            f"{description}\n"
            f"Автор: {author}"
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
        ocr_text = ""
        if self.canvas.ocr_overlay and (
            self.canvas.ocr_overlay.has_selection() or self.canvas.ocr_overlay.has_words()
        ):
            ocr_text = self.canvas.selected_ocr_text().strip()
        if ocr_text:
            QApplication.clipboard().setText(ocr_text)
            self.statusBar().showMessage("✓ Текст OCR скопирован", 2000)
            return

        self.logic.copy_to_clipboard()
        self.statusBar().showMessage("✓ Скриншот скопирован", 2000)

    def save_image(self):
        name = self.logic.save_image(self)
        if name:
            self.statusBar().showMessage(f"✓ Сохранено: {name}", 3000)

    def _cleanup_share_temp_file(self) -> None:
        temp_path = self._share_temp_file
        self._share_temp_file = None
        if temp_path is None:
            return
        try:
            temp_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("Failed to delete temporary share file '%s': %s", temp_path, exc)

    def _release_share_worker(self) -> None:
        worker = self._share_worker
        self._share_worker = None
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
        self._cleanup_share_temp_file()

    def share_image(self) -> None:
        if self._share_worker is not None and self._share_worker.isRunning():
            self.statusBar().showMessage("Загрузка уже выполняется...", 2500)
            return

        is_gif = self.logic.should_force_gif_output()
        suffix = ".gif" if is_gif else ".png"

        try:
            image = self.logic.export_image()
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка загрузки", f"Не удалось подготовить изображение: {exc}")
            return

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix="slipsnap_share_", suffix=suffix, delete=False
            ) as tmp:
                temp_path = Path(tmp.name)
            self._share_temp_file = temp_path

            if is_gif:
                saved = False
                animated_export = getattr(self.canvas, "save_animated_gif", None)
                if callable(animated_export):
                    try:
                        saved = bool(animated_export(temp_path, selected_only=False))
                    except TypeError:
                        saved = bool(animated_export(temp_path))
                    except Exception:
                        saved = False
                if not saved:
                    image.save(str(temp_path), format="GIF")
            else:
                image.save(str(temp_path), format="PNG")
        except Exception as exc:
            self._cleanup_share_temp_file()
            QMessageBox.warning(self, "Ошибка загрузки", f"Не удалось сохранить временный файл: {exc}")
            return

        from upload_service import UploadWorker
        worker = UploadWorker(temp_path)
        worker.finished.connect(self._on_share_done)
        worker.failed.connect(self._on_share_failed)
        self._share_worker = worker
        fmt = "GIF" if is_gif else "скриншот"
        self.statusBar().showMessage(f"Загружаю {fmt}...", 0)
        worker.start()

    def _on_share_done(self, url: str) -> None:
        self._release_share_worker()
        QApplication.clipboard().setText(url)
        self.statusBar().showMessage(f"Ссылка скопирована: {url}", 10000)
        QMessageBox.information(self, "Ссылка готова", f"Ссылка скопирована в буфер обмена:\n\n{url}")

    def _on_share_failed(self, msg: str) -> None:
        self._release_share_worker()
        self.statusBar().showMessage("Ошибка шеринга", 5000)
        QMessageBox.warning(self, "Ошибка загрузки", msg)

    def _update_collage_enabled(self):
        try:
            if hasattr(self, "act_collage"):
                self.act_collage.setEnabled(self.logic.collage_available())
        except Exception:
            pass

    # ---- OCR ----
    def _setup_ocr_button(self, button: QToolButton) -> None:
        self._ocr_menu = QMenu(button)
        button.setText("OCR")
        button.setToolTip("Распознать текст (правый клик — выбор языков)")
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(self._open_ocr_menu)
        self._refresh_ocr_menu()

    def _open_ocr_menu(self, pos) -> None:
        if self._ocr_menu is None or self._ocr_button is None:
            return
        self._refresh_ocr_menu()
        self._ocr_menu.exec(self._ocr_button.mapToGlobal(pos))

    def _refresh_ocr_menu(self) -> None:
        if self._ocr_menu is None:
            return
        self._ocr_menu.clear()
        try:
            available = get_available_languages()
        except OcrError as e:
            QMessageBox.warning(self, "SlipSnap · OCR", str(e))
            available = []
        preferred = [lang for lang in self.ocr_settings.preferred_languages if lang]
        selected_set = set(preferred)

        quick_codes = [
            ("rus", get_language_display_name("rus") or "Русский"),
            ("eng", get_language_display_name("eng") or "English"),
            ("chi_sim", get_language_display_name("chi_sim") or "中文"),
        ]

        container = QWidget(self._ocr_menu)
        container.setFixedWidth(260)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_row.setContentsMargins(0, 0, 0, 0)
        quick_buttons: dict[str, QToolButton] = {}

        def _apply_and_refresh(lang: str, checked: bool) -> None:
            self._update_ocr_language_selection(lang, checked, refresh_ui=False)
            selected_set.clear()
            selected_set.update(self.ocr_settings.preferred_languages)
            for code, button in quick_buttons.items():
                button.blockSignals(True)
                button.setChecked(code in selected_set)
                button.blockSignals(False)
            _populate(search_edit.text())

        flag_map = {
            "rus": "🇷🇺",
            "eng": "🇺🇸",
            "chi_sim": "🇨🇳",
        }

        for code, label in quick_codes:
            btn = QToolButton()
            btn.setText(flag_map.get(code, label))
            btn.setCheckable(True)
            btn.setChecked(code in selected_set)
            btn.setToolTip(label)
            btn.setFixedSize(40, 32)
            btn.setStyleSheet(
                "QToolButton {"
                "  border: 1px solid #d0d7de;"
                "  border-radius: 8px;"
                "  background: #f6f8fa;"
                "  font-size: 18px;"
                "}"
                "QToolButton:checked {"
                "  background: #e6f1ff;"
                "  border-color: #4c8bf5;"
                "}"
            )
            btn.toggled.connect(lambda checked, lang=code: _apply_and_refresh(lang, checked))
            quick_buttons[code] = btn
            quick_row.addWidget(btn)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        search_edit = QLineEdit(container)
        search_edit.setPlaceholderText("Поиск языка (Enter — добавить)")
        layout.addWidget(search_edit)

        list_widget = QListWidget(container)
        list_widget.setSelectionMode(QListWidget.NoSelection)
        list_widget.setMaximumHeight(180)
        layout.addWidget(list_widget)

        priority_codes = {code for code, _ in quick_codes}
        other_languages = sorted(set(lang for lang in available if lang not in priority_codes))

        def _populate(query: str) -> None:
            list_widget.blockSignals(True)
            list_widget.clear()
            normalized = query.strip().lower()
            for code in other_languages:
                display = get_language_display_name(code) or code
                if normalized and normalized not in code.lower() and normalized not in display.lower():
                    continue
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, code)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if code in selected_set else Qt.Unchecked)
                list_widget.addItem(item)
            if list_widget.count() == 0:
                placeholder = QListWidgetItem("Нет совпадений")
                placeholder.setFlags(Qt.NoItemFlags)
                list_widget.addItem(placeholder)
            list_widget.blockSignals(False)

        def _handle_list_change(item: QListWidgetItem) -> None:
            code = item.data(Qt.UserRole)
            if not code:
                return
            _apply_and_refresh(code, item.checkState() == Qt.Checked)

        _populate("")

        list_widget.itemChanged.connect(_handle_list_change)
        search_edit.textChanged.connect(_populate)
        search_edit.returnPressed.connect(lambda: _apply_and_refresh(search_edit.text().strip(), True))

        summary = QLabel(container)
        summary.setStyleSheet("color: #6e7781; font-size: 12px;")
        summary.setText("Можно выбрать несколько языков")
        layout.addWidget(summary)

        download_btn = QToolButton(container)
        download_btn.setText("Скачать языки…")
        download_btn.setStyleSheet(
            "QToolButton {"
            "  background: #eef2f7;"
            "  border: 1px solid #d0d7de;"
            "  border-radius: 8px;"
            "  padding: 6px 10px;"
            "}"
            "QToolButton:hover {"
            "  background: #e6f1ff;"
            "  border-color: #4c8bf5;"
            "}"
        )
        download_btn.clicked.connect(self._download_ocr_languages)
        layout.addWidget(download_btn)

        wrapper = QWidgetAction(self._ocr_menu)
        wrapper.setDefaultWidget(container)
        self._ocr_menu.addAction(wrapper)

    def _update_ocr_language_selection(self, language: str, checked: bool, *, refresh_ui: bool = True) -> None:
        languages = [lang for lang in self.ocr_settings.preferred_languages if lang != language]
        if checked:
            languages.append(language)
        if not languages:
            languages = [language]
        self._apply_ocr_languages(languages)
        if refresh_ui:
            self._refresh_ocr_menu()

    def _apply_ocr_languages(self, languages: list[str]) -> None:
        normalized = [str(lang).strip() for lang in languages if str(lang).strip()]
        if not normalized:
            normalized = ["eng"]
        self.ocr_settings.preferred_languages = list(dict.fromkeys(normalized))
        self.ocr_settings.last_language = "+".join(normalized)
        self.cfg["ocr_settings"] = self.ocr_settings.to_dict()
        save_config(self.cfg)

    def _download_ocr_languages(self) -> None:
        try:
            available = get_available_languages()
        except OcrError as exc:
            QMessageBox.warning(self, "SlipSnap · OCR", str(exc))
            return
        known_languages = sorted(set(LANGUAGE_DISPLAY_NAMES.keys()) | set(available))
        dialog = _OcrLanguageDownloadDialog(self, available, known_languages)
        if dialog.exec() != QDialog.Accepted:
            return
        codes = dialog.selected_languages()
        if not codes:
            QMessageBox.information(self, "SlipSnap · OCR", "Не указаны языки для загрузки.")
            return

        progress = QProgressDialog("Загрузка языков OCR…", "Отмена", 0, len(codes), self)
        progress.setWindowTitle("SlipSnap · OCR")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        def _progress(current: int, total: int, code: str) -> bool:
            progress.setMaximum(total)
            progress.setValue(current - 1)
            progress.setLabelText(f"Загружается {code}.traineddata ({current}/{total})")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            result = download_tesseract_languages(codes, progress=_progress, cfg=self.cfg)
        except OcrError as exc:
            progress.cancel()
            QMessageBox.warning(self, "SlipSnap · OCR", str(exc))
            return
        finally:
            progress.setValue(progress.maximum())

        summary_parts = []
        if result.installed:
            summary_parts.append("установлено: " + ", ".join(result.installed))
        if result.skipped:
            summary_parts.append("уже было: " + ", ".join(result.skipped))
        if result.failed:
            summary_parts.append("ошибка: " + ", ".join(result.failed))
        summary_text = "\n".join(summary_parts) if summary_parts else "Нет изменений."
        message = QMessageBox(self)
        message.setWindowTitle("SlipSnap · OCR")
        message.setIcon(QMessageBox.Information)
        message.setText(summary_text)
        if result.failed_details:
            details = "\n".join(f"{code}: {reason}" for code, reason in result.failed_details)
            message.setDetailedText(details)
        message.exec()
        self._refresh_ocr_menu()

    def _current_ocr_capture(self) -> Optional[OcrCapture]:
        try:
            capture = self.canvas.current_ocr_capture()
        except Exception:
            return None
        self._last_ocr_capture = capture
        return capture

    def _current_ocr_language_hint(self) -> str:
        languages = [lang for lang in self.ocr_settings.preferred_languages if str(lang).strip()]
        if not languages:
            languages = ["eng"]
            self._apply_ocr_languages(languages)
        return "+".join(languages)

    def _reset_ocr_state(self) -> None:
        """Remove previous OCR visuals before starting a new scan."""

        self._clear_ocr_toast()
        if self.canvas.ocr_overlay:
            self.canvas.ocr_overlay.clear()
            self.canvas.ocr_overlay.set_active(False)
        self.canvas.hide_ocr_scanner()

    def _start_ocr_scan(self, capture: OcrCapture) -> None:
        self._reset_ocr_state()
        self.canvas.show_ocr_scanner(capture.scene_rect)

    def _stop_ocr_scan(self, *, success: bool = True) -> None:
        color = QColor(ModernColors.SUCCESS if success else ModernColors.ERROR)
        self.canvas.hide_ocr_scanner(final_color=color)

    def _on_ocr_worker_finished(self, result: Optional[OcrResult], error: Optional[Exception]) -> None:
        worker = self._ocr_worker
        self._ocr_worker = None
        if worker:
            worker.deleteLater()

        self._stop_ocr_scan(success=error is None)

        if error:
            message = str(error)
            QMessageBox.warning(self, "SlipSnap · OCR", message)
            return

        if result is None:
            QMessageBox.warning(self, "SlipSnap · OCR", "Не удалось получить результат OCR.")
            return

        languages_used = result.languages_used or self.ocr_settings.preferred_languages
        self.ocr_settings.remember_run(self._last_ocr_language_hint, languages_used)
        self._apply_ocr_languages(self.ocr_settings.preferred_languages)
        self._handle_ocr_result(result)

    def _activate_ocr_text_mode(self) -> None:
        self.canvas.set_tool("ocr")

    def _clear_ocr_toast(self) -> None:
        if self._ocr_toast is None:
            return
        try:
            self.statusBar().removeWidget(self._ocr_toast)
        except Exception:
            pass
        self._ocr_toast.deleteLater()
        self._ocr_toast = None

    def _show_ocr_toast(self, result: OcrResult) -> None:
        self._ocr_toast_timer.stop()
        self._clear_ocr_toast()

        toast = QWidget(self)
        layout = QHBoxLayout(toast)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        headline = QLabel(
            "Текст распознан. Используйте Ctrl+C, чтобы сразу скопировать, или выделите курсором нужный фрагмент.",
            toast,
        )
        layout.addWidget(headline)

        meta_parts = []
        if result.language_tag:
            meta_parts.append(f"языки: {result.language_tag}")
        if result.fallback_used and result.missing_languages:
            meta_parts.append("нет пакетов: " + ", ".join(result.missing_languages))
        if meta_parts:
            meta = QLabel(" · ".join(meta_parts), toast)
            meta.setObjectName("metaLabel")
            layout.addWidget(meta)

        insert_btn = QToolButton(toast)
        insert_btn.setText("Вставить на холст")
        insert_btn.clicked.connect(lambda: self._insert_ocr_text(result.text))
        layout.addWidget(insert_btn)

        close_btn = QToolButton(toast)
        close_btn.setText("✕")
        close_btn.clicked.connect(self._clear_ocr_toast)
        layout.addWidget(close_btn)

        toast.setObjectName("ocrToast")
        toast.setStyleSheet(
            "#ocrToast {"
            "  background: rgba(255, 255, 255, 0.92);"
            "  border: 1px solid rgba(0, 0, 0, 0.08);"
            "  border-radius: 10px;"
            "  padding: 2px;"
            "}"
            "#ocrToast QLabel { color: #1f1f1f; }"
            "#ocrToast #metaLabel { color: #5f6368; font-size: 12px; }"
            "#ocrToast QToolButton { border: none; padding: 6px 10px; }"
            "#ocrToast QToolButton:hover { background: rgba(0, 0, 0, 0.04); border-radius: 6px; }"
        )

        self.statusBar().addPermanentWidget(toast, 1)
        self._ocr_toast = toast
        self._ocr_toast_timer.start(7000)

    def _handle_ocr_result(self, result: OcrResult) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(result.text)

        status_parts = ["OCR: текст скопирован"]
        if result.language_tag:
            status_parts.append(f"язык: {result.language_tag}")
        if result.fallback_used and result.missing_languages:
            status_parts.append("нет пакетов: " + ", ".join(result.missing_languages))
        status = " | ".join(status_parts)
        self.statusBar().showMessage(status, 5000)

        if not result.text:
            QMessageBox.information(self, "SlipSnap · OCR", "Текст не найден на изображении.")
            return

        if self._last_ocr_capture and self.canvas.ocr_overlay:
            self.canvas.ocr_overlay.apply_result(result, self._last_ocr_capture)

        self._activate_ocr_text_mode()
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._show_ocr_toast(result)

    def _insert_ocr_text(self, text: str) -> None:
        if not text.strip():
            return
        pos = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        item = self.text_manager.create_text_item(pos, text.strip())
        if item:
            self.canvas.undo_stack.push(AddCommand(self.canvas.scene, item))
            self.canvas.update_scene_rect()

    def rerun_ocr_with_language(self):
        if self._ocr_worker:
            return

        self._reset_ocr_state()
        capture = self._current_ocr_capture()
        if capture is None:
            QMessageBox.warning(self, "SlipSnap · OCR", "Нет изображения для распознавания.")
            return

        lang_choice = self._current_ocr_language_hint()
        self._last_ocr_language_hint = lang_choice
        self._start_ocr_scan(capture)

        worker = _OcrWorker(capture, self.ocr_settings, lang_choice)
        worker.finished.connect(self._on_ocr_worker_finished)
        self._ocr_worker = worker
        worker.start()

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
        pixmap = self._rounded_pixmap(qimg)
        screenshot_item = HighQualityPixmapItem(pixmap.toImage())
        screenshot_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        screenshot_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        screenshot_item.setZValue(10)
        screenshot_item.setData(0, item_tag)
        self.canvas.scene.addItem(screenshot_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, screenshot_item))
        self._position_new_item(screenshot_item)

    def _position_new_item(self, item: QGraphicsItem) -> None:
        view_center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
        rect = item.boundingRect()
        item.setPos(view_center.x() - rect.width() / 2, view_center.y() - rect.height() / 2)
        self.canvas.scene.clearSelection()
        item.setSelected(True)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_collage_enabled()
        self.canvas._apply_lock_state()
        self.canvas.update_scene_rect()

    def _insert_gif_item(self, path: Path, item_tag: str = "gif") -> bool:
        gif_path = Path(path)
        try:
            gif_item = _AnimatedGifItem(gif_path)
        except Exception as exc:
            logger.warning("Failed to create GIF scene item from '%s': %s", gif_path, exc)
            return False

        gif_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        gif_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        gif_item.setFlag(QGraphicsItem.ItemIsFocusable, True)
        gif_item.setZValue(10)
        gif_item.setData(0, item_tag)
        gif_item.setData(1, "gif")
        gif_item.setData(2, str(gif_path))
        self.canvas.scene.addItem(gif_item)
        self.canvas.undo_stack.push(AddCommand(self.canvas.scene, gif_item))
        self._position_new_item(gif_item)
        return True

    def _materialize_clipboard_gif(self, gif_bytes: bytes) -> Optional[Path]:
        if not gif_bytes:
            return None
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="slipsnap_clip_gif_"))
            target = temp_dir / "clipboard.gif"
            target.write_bytes(gif_bytes)
        except Exception as exc:
            logger.warning("Failed to materialize GIF from clipboard bytes: %s", exc)
            return None
        self._clipboard_temp_dirs.append(temp_dir)
        return target

    def _paste_gif_from_mime(self, mime: QMimeData | None) -> bool:
        gif_paths = gif_paths_from_mime(mime)
        if not gif_paths:
            gif_bytes = gif_bytes_from_mime(mime)
            if gif_bytes:
                materialized = self._materialize_clipboard_gif(gif_bytes)
                if materialized is not None:
                    gif_paths = [materialized]
        inserted = False
        for gif_path in gif_paths:
            if self._insert_gif_item(gif_path, item_tag="gif"):
                inserted = True
        if gif_paths and not inserted:
            logger.warning("GIF payload detected but no GIF items were inserted (%d candidates).", len(gif_paths))
        return inserted

    def _paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if self._paste_gif_from_mime(mime):
            return True
        images = images_from_mime(mime)
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
        if path.suffix.lower() == ".gif":
            if not self._insert_gif_item(path, item_tag="meme_gif"):
                QMessageBox.warning(self, "Ошибка", "Не удалось загрузить GIF мем.")
                return
            self.statusBar().showMessage("◉ GIF мем добавлен на холст", 2500)
            return

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
        worker = self._share_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.wait(3000)
            except Exception:
                pass
        self._release_share_worker()

        for temp_dir in self._clipboard_temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
        self._clipboard_temp_dirs.clear()
        if hasattr(self, "canvas"):
            self.canvas._cleanup_temp_dirs()
        super().closeEvent(event)

