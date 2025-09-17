from pathlib import Path

from PIL import Image
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog

from clipboard_utils import copy_pil_image_to_clipboard
from logic import HISTORY_DIR


class EditorLogic:
    def __init__(self, canvas, live_manager):
        self.canvas = canvas
        self.live_manager = live_manager

    def export_image(self) -> Image.Image:
        return self.canvas.export_image()

    def copy_to_clipboard(self):
        text = ""
        if self.live_manager:
            try:
                text = (self.live_manager.selected_text() or "").strip()
            except Exception:
                text = ""

        if text:
            QGuiApplication.clipboard().setText(text)
            return "text"

        if self.canvas.scene.selectedItems():
            img = self.canvas.export_selection()
            copy_pil_image_to_clipboard(img)
            return "selection"

        img = self.export_image()
        copy_pil_image_to_clipboard(img)
        return "image"

    def save_image(self, parent):
        img = self.export_image()
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить изображение",
            "",
            "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)",
        )
        if not path:
            return None
        if path.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        img.save(path)
        return Path(path).name

    def toggle_live_text(self):
        if not self.live_manager:
            return "error"
        if self.live_manager.active:
            self.live_manager.disable()
            return "disabled"
        if self.live_manager.enable():
            return "enabled"
        return "error"

    def collage_available(self):
        return any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(
            HISTORY_DIR.glob("*.jpeg")
        )
