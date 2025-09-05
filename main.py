from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from gui import App

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SlipSnap")

    icon_path = Path(__file__).resolve().with_name("SlipSnap.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    global _APP_CTX
    _APP_CTX = App()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
