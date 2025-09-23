from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)


class TeamsSettingsDialog(QDialog):
    """Dialog that lets the user configure Microsoft Teams integration."""

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self.setWindowTitle("Настройки Microsoft Teams")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Укажите отображаемое имя и адрес входящего вебхука Teams.\n"
            "URL можно создать в канале Microsoft Teams через пункт"
            " «Подключить вебхуки»."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        self.name_edit = QLineEdit(cfg.get("teams_user_name", ""))
        self.email_edit = QLineEdit(cfg.get("teams_user_email", ""))
        self.webhook_edit = QLineEdit(cfg.get("teams_webhook_url", ""))
        self.webhook_edit.setPlaceholderText("https://outlook.office.com/webhook/…")

        form.addRow("Имя в Teams", self.name_edit)
        form.addRow("Электронная почта", self.email_edit)
        form.addRow("Webhook URL", self.webhook_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        webhook = self.webhook_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Microsoft Teams", "Укажите имя, отображаемое в Teams.")
            self.name_edit.setFocus()
            return

        if not webhook:
            QMessageBox.warning(self, "Microsoft Teams", "Укажите адрес входящего вебхука Teams.")
            self.webhook_edit.setFocus()
            return

        super().accept()

    def values(self) -> dict:
        return {
            "teams_user_name": self.name_edit.text().strip(),
            "teams_user_email": self.email_edit.text().strip(),
            "teams_webhook_url": self.webhook_edit.text().strip(),
        }
