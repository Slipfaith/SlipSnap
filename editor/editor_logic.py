from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QFileDialog

from clipboard_utils import copy_pil_image_to_clipboard
from logic import HISTORY_DIR, save_config


class EditorLogic:
    def __init__(self, canvas, cfg: dict | None = None):
        self.canvas = canvas
        self._cfg = cfg
        saved = (cfg or {}).get("last_save_directory", "")
        directory = Path(saved) if saved else Path.home()
        self._last_save_directory = directory if directory.is_dir() else Path.home()

    def export_image(self) -> Image.Image:
        return self.canvas.export_image()

    def copy_to_clipboard(self):
        img = self.export_image()
        copy_pil_image_to_clipboard(img)
        return "image"

    def save_image(self, parent):
        img = self.export_image()
        default_name = self._next_snap_name(self._last_save_directory)
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить изображение",
            str(default_name),
            "PNG (*.png);;JPEG (*.jpg);;Все файлы (*.*)",
        )
        if not path:
            return None
        if path.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        img.save(path)
        self._last_save_directory = Path(path).parent
        self._persist_save_directory()
        return Path(path).name

    def next_snap_filename(self) -> str:
        return self._next_snap_name(self._last_save_directory).name

    def _next_snap_name(self, directory: Path) -> Path:
        if not directory.is_dir():
            directory = Path.home()
        existing_numbers = []
        for ext in ("png", "jpg", "jpeg"):
            for file in directory.glob(f"snap_*.{ext}"):
                suffix = file.stem.removeprefix("snap_")
                if suffix.isdigit():
                    existing_numbers.append(int(suffix))

        next_number = max(existing_numbers, default=0) + 1
        return directory / f"snap_{next_number:02d}.png"

    def _persist_save_directory(self):
        if self._cfg is not None:
            self._cfg["last_save_directory"] = str(self._last_save_directory)
            save_config(self._cfg)

    def collage_available(self):
        return any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(
            HISTORY_DIR.glob("*.jpeg")
        )
