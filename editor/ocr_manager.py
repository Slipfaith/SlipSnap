from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QTimer, Signal, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from editor.ocr_overlay import OcrCapture
from logic import save_config
from ocr import (
    OcrError,
    OcrResult,
    OcrSettings,
    get_available_languages,
    get_language_display_name,
    run_ocr,
)

from editor.ui.styles import ModernColors
from editor.undo_commands import AddCommand


if TYPE_CHECKING:
    from editor.editor_window import EditorWindow


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
            result = run_ocr(
                self.capture.image.copy(), self.settings, language_hint=self.language_hint
            )
        except Exception as exc:  # noqa: BLE001
            error = exc
        self.finished.emit(result, error)


class _LanguagePickerDialog(QDialog):
    """Modern dialog for selecting OCR languages."""

    def __init__(
        self,
        parent: QWidget,
        available: list[str],
        default_lang: str,
        preferred: list[str],
    ):
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
        priority_block.setStyleSheet(
            "QFrame { border: 1px solid #d0d7de; border-radius: 10px; }"
        )
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
            cb.toggled.connect(
                lambda checked, lang=code: self._toggle_language(lang, checked)
            )
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

        available_text = (
            ", ".join(self._available) if self._available else "нет установленных языков"
        )
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
            selected_codes = [
                code.strip() for code in default_lang.split("+") if code.strip()
            ]
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
        other_languages = [
            code for code in self._available if code not in self._priority_codes
        ]
        for code in other_languages:
            display = get_language_display_name(code)
            if normalized_query and normalized_query not in code.lower() and (
                display and normalized_query not in display.lower()
            ):
                continue
            item = QListWidgetItem(display or code)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if code in self._selected_languages else Qt.Unchecked
            )
            self.list_widget.addItem(item)
        if self.list_widget.count() == 0:
            placeholder = QListWidgetItem("Нет совпадений")
            placeholder.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(
                    Qt.Checked
                    if item.data(Qt.UserRole) in self._selected_languages
                    else Qt.Unchecked
                )

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

    def _toggle_language(
        self, language: str, checked: bool, refresh_list: bool = True
    ) -> None:
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

        ordered = [
            code for code in self._priority_codes if code in self._selected_languages
        ]
        ordered.extend(
            sorted(
                lang
                for lang in self._selected_languages
                if lang not in self._priority_codes
            )
        )
        return "+".join(ordered)


class OcrManager:
    def __init__(self, editor_window: EditorWindow):
        self._editor_window = editor_window
        self._canvas = editor_window.canvas
        self._cfg = editor_window.cfg
        self._text_manager = editor_window.text_manager

        self.ocr_settings = OcrSettings.from_config(self._cfg)
        self._last_ocr_capture: Optional[OcrCapture] = None
        self._last_ocr_language_hint: str = ""
        self._ocr_worker: Optional[_OcrWorker] = None
        self._ocr_toast: Optional[QWidget] = None
        self._ocr_toast_timer = QTimer(self._editor_window)
        self._ocr_toast_timer.setSingleShot(True)
        self._ocr_toast_timer.timeout.connect(self._clear_ocr_toast)
        self._ocr_menu: Optional[QMenu] = None
        self._ocr_button: Optional[QToolButton] = None

    def setup(self, ocr_button: QToolButton):
        self._ocr_button = ocr_button
        if self._ocr_button is not None:
            self._setup_ocr_button(self._ocr_button)

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
            QMessageBox.warning(self._editor_window, "SlipSnap · OCR", str(e))
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
            btn.toggled.connect(
                lambda checked, lang=code: _apply_and_refresh(lang, checked)
            )
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
        other_languages = sorted(
            set(lang for lang in available if lang not in priority_codes)
        )

        def _populate(query: str) -> None:
            list_widget.blockSignals(True)
            list_widget.clear()
            normalized = query.strip().lower()
            for code in other_languages:
                display = get_language_display_name(code) or code
                if (
                    normalized
                    and normalized not in code.lower()
                    and normalized not in display.lower()
                ):
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
        search_edit.returnPressed.connect(
            lambda: _apply_and_refresh(search_edit.text().strip(), True)
        )

        summary = QLabel(container)
        summary.setStyleSheet("color: #6e7781; font-size: 12px;")
        summary.setText("Можно выбрать несколько языков")
        layout.addWidget(summary)

        wrapper = QWidgetAction(self._ocr_menu)
        wrapper.setDefaultWidget(container)
        self._ocr_menu.addAction(wrapper)

    def _update_ocr_language_selection(
        self, language: str, checked: bool, *, refresh_ui: bool = True
    ) -> None:
        languages = [
            lang for lang in self.ocr_settings.preferred_languages if lang != language
        ]
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
        self._cfg["ocr_settings"] = self.ocr_settings.to_dict()
        save_config(self._cfg)

    def _current_ocr_capture(self) -> Optional[OcrCapture]:
        try:
            capture = self._canvas.current_ocr_capture()
        except Exception:
            return None
        self._last_ocr_capture = capture
        return capture

    def _current_ocr_language_hint(self) -> str:
        languages = [
            lang for lang in self.ocr_settings.preferred_languages if str(lang).strip()
        ]
        if not languages:
            languages = ["eng"]
            self._apply_ocr_languages(languages)
        return "+".join(languages)

    def _start_ocr_scan(self, capture: OcrCapture) -> None:
        if self._canvas.ocr_overlay:
            self._canvas.ocr_overlay.clear()
            self._canvas.ocr_overlay.set_active(False)
        self._canvas.show_ocr_scanner(capture.scene_rect)

    def _stop_ocr_scan(self, *, success: bool = True) -> None:
        color = QColor(ModernColors.SUCCESS if success else ModernColors.ERROR)
        self._canvas.hide_ocr_scanner(final_color=color)

    def _on_ocr_worker_finished(
        self, result: Optional[OcrResult], error: Optional[Exception]
    ) -> None:
        worker = self._ocr_worker
        self._ocr_worker = None
        if worker:
            worker.deleteLater()

        self._stop_ocr_scan(success=error is None)

        if error:
            message = str(error)
            QMessageBox.warning(self._editor_window, "SlipSnap · OCR", message)
            return

        if result is None:
            QMessageBox.warning(
                self._editor_window, "SlipSnap · OCR", "Не удалось получить результат OCR."
            )
            return

        languages_used = result.languages_used or self.ocr_settings.preferred_languages
        self.ocr_settings.remember_run(self._last_ocr_language_hint, languages_used)
        self._apply_ocr_languages(self.ocr_settings.preferred_languages)
        self._handle_ocr_result(result)

    def _activate_ocr_text_mode(self) -> None:
        self._canvas.set_tool("ocr")

    def _clear_ocr_toast(self) -> None:
        if self._ocr_toast is None:
            return
        try:
            self._editor_window.statusBar().removeWidget(self._ocr_toast)
        except Exception:
            pass
        self._ocr_toast.deleteLater()
        self._ocr_toast = None

    def _show_ocr_toast(self, result: OcrResult) -> None:
        self._ocr_toast_timer.stop()
        self._clear_ocr_toast()

        toast = QWidget(self._editor_window)
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

        self._editor_window.statusBar().addPermanentWidget(toast, 1)
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
        self._editor_window.statusBar().showMessage(status, 5000)

        if not result.text:
            QMessageBox.information(
                self._editor_window, "SlipSnap · OCR", "Текст не найден на изображении."
            )
            return

        if self._last_ocr_capture and self._canvas.ocr_overlay:
            self._canvas.ocr_overlay.apply_result(result, self._last_ocr_capture)

        self._activate_ocr_text_mode()
        self._canvas.setFocus(Qt.OtherFocusReason)
        self._show_ocr_toast(result)

    def _insert_ocr_text(self, text: str) -> None:
        if not text.strip():
            return
        pos = self._canvas.mapToScene(self._canvas.viewport().rect().center())
        item = self._text_manager.create_text_item(pos, text.strip())
        if item:
            self._canvas.undo_stack.push(AddCommand(self._canvas.scene, item))
            self._canvas.update_scene_rect()

    def rerun_ocr_with_language(self):
        if self._ocr_worker:
            return

        capture = self._current_ocr_capture()
        if capture is None:
            QMessageBox.warning(
                self._editor_window,
                "SlipSnap · OCR",
                "Нет изображения для распознавания.",
            )
            return

        lang_choice = self._current_ocr_language_hint()
        self._last_ocr_language_hint = lang_choice
        self._start_ocr_scan(capture)

        worker = _OcrWorker(capture, self.ocr_settings, lang_choice)
        worker.finished.connect(self._on_ocr_worker_finished)
        self._ocr_worker = worker
        worker.start()

    def copy_to_clipboard(self):
        ocr_text = ""
        if self._canvas.ocr_overlay and (
            self._canvas.ocr_overlay.has_selection()
            or self._canvas.ocr_overlay.has_words()
        ):
            ocr_text = self._canvas.selected_ocr_text().strip()
        if ocr_text:
            QApplication.clipboard().setText(ocr_text)
            self._editor_window.statusBar().showMessage("✓ Текст OCR скопирован", 2000)
            return True
        return False
