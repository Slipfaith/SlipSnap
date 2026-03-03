# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

_UPLOAD_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
_CONNECT_TIMEOUT_SEC = 10
_READ_TIMEOUT_SEC = 120
_MAX_ATTEMPTS = 3


class UploadWorker(QThread):
    finished = Signal(str)  # URL on success
    failed = Signal(str)    # user-facing error message

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)

    @staticmethod
    def _error_hint() -> str:
        return "Проверьте интернет/впн и повторите попытку через минуту."

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return min(2.5, 0.7 * attempt)

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

            try:
                file_bytes = self.file_path.read_bytes()
            except OSError as exc:
                self.failed.emit(f"Не удалось прочитать файл для загрузки: {exc}")
                return

            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    response = requests.post(
                        _UPLOAD_URL,
                        data={"reqtype": "fileupload", "time": "24h"},
                        files={"fileToUpload": (self.file_path.name, file_bytes)},
                        timeout=(_CONNECT_TIMEOUT_SEC, _READ_TIMEOUT_SEC),
                    )
                except requests.exceptions.Timeout:
                    if attempt < _MAX_ATTEMPTS:
                        time.sleep(self._retry_delay(attempt))
                        continue
                    self.failed.emit(
                        "Сервер загрузки долго не отвечает. "
                        f"{self._error_hint()}"
                    )
                    return
                except requests.exceptions.ConnectionError:
                    if attempt < _MAX_ATTEMPTS:
                        time.sleep(self._retry_delay(attempt))
                        continue
                    self.failed.emit(
                        "Не удалось подключиться к серверу загрузки. "
                        f"{self._error_hint()}"
                    )
                    return
                except requests.exceptions.RequestException as exc:
                    self.failed.emit(f"Ошибка сети при загрузке: {exc}")
                    return

                if response.status_code != 200:
                    if 500 <= response.status_code < 600 and attempt < _MAX_ATTEMPTS:
                        time.sleep(self._retry_delay(attempt))
                        continue
                    self.failed.emit(f"Ошибка сервера: HTTP {response.status_code}")
                    return

                url = response.text.strip()
                if not url.startswith("http"):
                    self.failed.emit(f"Неожиданный ответ сервера: {url}")
                    return

                self.finished.emit(url)
                return

            self.failed.emit("Не удалось загрузить файл. Попробуйте позже.")
        except Exception as exc:
            self.failed.emit(f"Ошибка загрузки: {exc}")
