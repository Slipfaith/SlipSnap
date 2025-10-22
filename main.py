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

    def acquire_lock(wait_ms: int = 1000) -> bool:
        if lock_file.tryLock(wait_ms):
            return True
        if lock_file.removeStaleLockFile():
            return lock_file.tryLock(0)
        return False

    if not acquire_lock():
        while True:
            msg = QMessageBox()
            msg.setWindowTitle("SlipSnap уже запущен")
            msg.setIcon(QMessageBox.Information)
            msg.setText(
                "Нельзя запустить вторую копию приложения, так как SlipSnap уже работает."
            )
            msg.setInformativeText(
                "Если предыдущий запуск завершился сбоем, попробуйте сбросить блокировку."
            )
            reset_button = msg.addButton("Сбросить блокировку", QMessageBox.ActionRole)
            retry_button = msg.addButton("Повторить", QMessageBox.AcceptRole)
            cancel_button = msg.addButton(QMessageBox.Cancel)
            msg.setDefaultButton(retry_button)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == cancel_button:
                return
            if clicked == reset_button:
                if acquire_lock(0):
                    break
            elif clicked == retry_button:
                if acquire_lock():
                    break
            else:
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
