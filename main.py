from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, QDir

from gui import App

_LOCK_FILE = None


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SlipSnap")

    lock_file_path = Path(QDir.tempPath()) / "SlipSnap.lock"
    lock_file = QLockFile(str(lock_file_path))
    lock_file.setStaleLockTime(0)
    if not lock_file.tryLock(1000):  # ждёт 1 секунду
        QMessageBox.information(
            None,
            "SlipSnap уже запущен",
            "Нельзя запустить вторую копию приложения, так как SlipSnap уже работает.",
        )
        returnсто

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
