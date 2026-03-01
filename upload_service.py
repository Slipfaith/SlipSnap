# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class UploadWorker(QThread):
    finished = Signal(str)  # URL on success
    failed = Signal(str)    # user-facing error message

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)

    def run(self) -> None:
        try:
            if not self.file_path.exists():
                self.failed.emit("Не удалось найти файл для загрузки.")
                return

            try:
                import requests
            except Exception:
                self.failed.emit("Модуль requests не установлен.")
                return

            file_bytes = self.file_path.read_bytes()
            response = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "24h"},
                files={"fileToUpload": (self.file_path.name, file_bytes)},
                timeout=30,
            )

            if response.status_code != 200:
                self.failed.emit(f"Ошибка сервера: HTTP {response.status_code}")
                return

            url = response.text.strip()
            if not url.startswith("http"):
                self.failed.emit(f"Неожиданный ответ сервера: {url}")
                return

            self.finished.emit(url)
        except Exception as exc:
            self.failed.emit(f"Ошибка загрузки: {exc}")
