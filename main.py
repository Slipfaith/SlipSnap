from PySide6.QtWidgets import QApplication
import sys
from gui import App

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Screenshot")
    global _APP_CTX
    _APP_CTX = App()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()