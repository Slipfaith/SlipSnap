from pathlib import Path
from PIL import Image, ImageQt
from PySide6.QtWidgets import QApplication, QFileDialog

from logic import HISTORY_DIR


class EditorLogic:
    def __init__(self, canvas, ocr_manager, live_manager):
        self.canvas = canvas
        self.ocr_manager = ocr_manager
        self.live_manager = live_manager

    def export_image(self) -> Image.Image:
        return self.canvas.export_image()

    def copy_to_clipboard(self):
        img = self.export_image()
        qim = ImageQt.ImageQt(img)
        QApplication.clipboard().setImage(qim)

    def save_image(self, parent):
        img = self.export_image()
        path, _ = QFileDialog.getSaveFileName(
            parent, "Сохранить изображение", "",
            "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)")
        if not path:
            return None
        if path.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        img.save(path)
        return Path(path).name

    def ocr_current(self, parent):
        img = self.export_image()
        return self.ocr_manager.ocr_to_clipboard(img, parent)

    def toggle_live_text(self):
        return self.live_manager.toggle()

    def copy_live_text(self, parent):
        if self.live_manager.active and self.live_manager.copy_selection_to_clipboard():
            return "live"
        img = self.export_image()
        if self.ocr_manager.ocr_to_clipboard(img, parent):
            return "ocr"
        return None

    def collage_available(self):
        return any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(HISTORY_DIR.glob("*.jpeg"))
