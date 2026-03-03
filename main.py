# -*- coding: utf-8 -*-
import logging
import os
from pathlib import Path
import sys
from typing import List, Optional

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, QDir

from gui import App

APP_NAME = "SlipSnap"
APP_VERSION = "3.0"  # Меняй версию программы только здесь.
APP_DESCRIPTION = "Современный редактор скриншотов"
APP_AUTHOR = "slipfaith"

_LOCK_FILE = None


def _configure_logging() -> None:
    level_name = str(os.getenv("SLIPSNAP_LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_path = Path(QDir.tempPath()) / f"{APP_NAME}.log"

    handlers: List[logging.Handler] = [logging.StreamHandler()]
    file_handler: Optional[logging.Handler] = None
    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except Exception:
        file_handler = None
    if file_handler is not None:
        handlers.append(file_handler)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)

    logging.captureWarnings(True)
    logging.getLogger(__name__).info(
        "Logging configured (level=%s, file=%s)",
        logging.getLevelName(level),
        str(log_path) if file_handler is not None else "disabled",
    )


def main():
    _configure_logging()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    app.setProperty("app_description", APP_DESCRIPTION)
    app.setProperty("app_author", APP_AUTHOR)

    lock_file_path = Path(QDir.tempPath()) / f"{APP_NAME}.lock"
    lock_file = QLockFile(str(lock_file_path))
    lock_file.setStaleLockTime(0)
    if not lock_file.tryLock(1000):  # ждёт 1 секунду
        QMessageBox.information(
            None,
            f"{APP_NAME} уже запущен",
            f"Нельзя запустить вторую копию приложения, так как {APP_NAME} уже работает.",
        )
        return

    global _LOCK_FILE
    _LOCK_FILE = lock_file

    icon_path = Path(__file__).resolve().with_name("SlipSnap.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    global _APP_CTX
    _APP_CTX = App()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
