# -*- coding: utf-8 -*-
"""Dialog for managing Mistral and Gemini OCR credentials."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from api_key_store import (
    ApiKeyStoreError,
    delete_api_key,
    get_api_key_status,
    set_api_key,
)
from cloud_ocr import PROVIDER_NAMES, check_cloud_provider


class _ConnectionTestWorker(QThread):
    completed = Signal(str, object)

    def __init__(self, provider: str, api_key: str, parent: QWidget):
        super().__init__(parent)
        self.provider = provider
        self.api_key = api_key

    def run(self) -> None:
        error = None
        try:
            check_cloud_provider(self.provider, self.api_key or None)
        except Exception as exc:  # noqa: BLE001 - passed to the GUI thread for display
            error = exc
        self.completed.emit(self.provider, error)


class OcrCloudSettingsDialog(QDialog):
    """Edit API keys without exposing their saved values in the UI or config."""

    _PROVIDERS = ("mistral", "gemini")

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("ocrCloudSettingsDialog")
        self.setWindowTitle("SlipSnap · Облачный OCR")
        self.setMinimumWidth(510)
        self._editors: dict[str, QLineEdit] = {}
        self._statuses: dict[str, QLabel] = {}
        self._test_buttons: dict[str, QPushButton] = {}
        self._worker: _ConnectionTestWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        intro = QLabel(
            "Ключи сохраняются в диспетчере учётных данных Windows и не попадают "
            "в .slipsnap_config.json. Сохранённый ключ повторно не показывается.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        for provider in self._PROVIDERS:
            layout.addWidget(self._provider_group(provider))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _provider_group(self, provider: str) -> QGroupBox:
        group = QGroupBox(PROVIDER_NAMES[provider], self)
        form = QFormLayout(group)

        editor = QLineEdit(group)
        editor.setObjectName(f"{provider}ApiKeyEdit")
        editor.setEchoMode(QLineEdit.Password)
        editor.setClearButtonEnabled(True)
        editor.setPlaceholderText("Вставьте новый API-ключ")
        self._editors[provider] = editor
        form.addRow("API-ключ:", editor)

        controls = QWidget(group)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        status = QLabel(controls)
        self._statuses[provider] = status
        controls_layout.addWidget(status, 1)

        test_button = QPushButton("Проверить", controls)
        test_button.clicked.connect(lambda _checked=False, item=provider: self._test(item))
        self._test_buttons[provider] = test_button
        controls_layout.addWidget(test_button)

        delete_button = QPushButton("Удалить ключ", controls)
        delete_button.clicked.connect(lambda _checked=False, item=provider: self._delete(item))
        controls_layout.addWidget(delete_button)
        form.addRow("", controls)
        self._refresh_status(provider)
        return group

    def _refresh_status(self, provider: str) -> None:
        try:
            status = get_api_key_status(provider)
        except ApiKeyStoreError as exc:
            self._statuses[provider].setText(str(exc))
            return
        if status.available:
            self._statuses[provider].setText(f"Ключ задан · источник: {status.source}")
        else:
            self._statuses[provider].setText("Ключ не задан")

    def _test(self, provider: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        key = self._editors[provider].text().strip()
        self._set_test_buttons_enabled(False)
        self._statuses[provider].setText("Проверка подключения…")
        worker = _ConnectionTestWorker(provider, key, self)
        worker.completed.connect(self._test_finished)
        self._worker = worker
        worker.start()

    def _test_finished(self, provider: str, error: Exception | None) -> None:
        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()
        self._set_test_buttons_enabled(True)
        if error is None:
            self._statuses[provider].setText("Подключение работает")
        else:
            self._statuses[provider].setText(f"Ошибка: {error}")

    def _set_test_buttons_enabled(self, enabled: bool) -> None:
        for button in self._test_buttons.values():
            button.setEnabled(enabled)

    def _delete(self, provider: str) -> None:
        reply = QMessageBox.question(
            self,
            "SlipSnap · Облачный OCR",
            f"Удалить сохранённый ключ {PROVIDER_NAMES[provider]}?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            delete_api_key(provider)
        except ApiKeyStoreError as exc:
            QMessageBox.warning(self, "SlipSnap · Облачный OCR", str(exc))
            return
        self._editors[provider].clear()
        self._refresh_status(provider)

    def _save_and_accept(self) -> None:
        try:
            for provider, editor in self._editors.items():
                key = editor.text().strip()
                if key:
                    set_api_key(provider, key)
        except (ApiKeyStoreError, ValueError) as exc:
            QMessageBox.warning(self, "SlipSnap · Облачный OCR", str(exc))
            return
        self.accept()

    def reject(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(
                self,
                "SlipSnap · Облачный OCR",
                "Дождитесь завершения проверки подключения.",
            )
            return
        super().reject()
