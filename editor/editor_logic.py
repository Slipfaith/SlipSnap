# -*- coding: utf-8 -*-
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

    def should_force_gif_output(self) -> bool:
        detector = getattr(self.canvas, "has_gif_content", None)
        if callable(detector):
            try:
                return bool(detector())
            except Exception:
                return False
        return False

    def copy_to_clipboard(self):
        img = self.export_image()
        copy_pil_image_to_clipboard(img)
        return "image"

    def save_image(self, parent):
        img = self.export_image()
        force_gif = self.should_force_gif_output()
        preferred_ext = ".gif" if force_gif else ".png"
        default_name = self._next_snap_name(self._last_save_directory, preferred_ext=preferred_ext)
        filters = "GIF (*.gif)" if force_gif else "PNG (*.png);;JPEG (*.jpg);;GIF (*.gif);;Все файлы (*.*)"
        default_filter = "GIF (*.gif)" if force_gif else "PNG (*.png)"
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить изображение",
            str(default_name),
            filters,
            default_filter,
        )
        if not path:
            return None

        target = Path(path)
        suffix = target.suffix.lower()
        if force_gif:
            target = target.with_suffix(".gif")
            saved = False
            animated_export = getattr(self.canvas, "save_animated_gif", None)
            if callable(animated_export):
                try:
                    saved = bool(animated_export(target, selected_only=False))
                except TypeError:
                    saved = bool(animated_export(target))
                except Exception:
                    saved = False
            if not saved:
                img.save(target, format="GIF")
        elif suffix in {".jpg", ".jpeg"}:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(target, format="JPEG")
        elif suffix == ".gif":
            target = target.with_suffix(".gif")
            img.save(target, format="GIF")
        else:
            target = target.with_suffix(".png")
            img.save(target, format="PNG")

        self._last_save_directory = target.parent
        self._persist_save_directory()
        return target.name

    def next_snap_filename(self, extension: str = ".png") -> str:
        return self._next_snap_name(self._last_save_directory, preferred_ext=extension).name

    def next_snap_filename_for_directory(self, directory: Path | str | None, extension: str = ".png") -> str:
        if directory is None:
            target_dir = self._last_save_directory
        else:
            target_dir = Path(directory)
        return self._next_snap_name(target_dir, preferred_ext=extension).name

    def _next_snap_name(self, directory: Path, preferred_ext: str = ".png") -> Path:
        if not directory.is_dir():
            directory = Path.home()
        ext = preferred_ext if preferred_ext.startswith(".") else f".{preferred_ext}"
        if ext.lower() not in {".png", ".jpg", ".jpeg", ".gif"}:
            ext = ".png"

        existing_numbers = []
        for scan_ext in ("png", "jpg", "jpeg", "gif"):
            for file in directory.glob(f"snap_*.{scan_ext}"):
                suffix = file.stem.removeprefix("snap_")
                if suffix.isdigit():
                    existing_numbers.append(int(suffix))

        next_number = max(existing_numbers, default=0) + 1
        return directory / f"snap_{next_number:02d}{ext.lower()}"

    def _persist_save_directory(self):
        if self._cfg is not None:
            self._cfg["last_save_directory"] = str(self._last_save_directory)
            save_config(self._cfg)

    def collage_available(self):
        return any(HISTORY_DIR.glob("*.png")) or any(HISTORY_DIR.glob("*.jpg")) or any(
            HISTORY_DIR.glob("*.jpeg")
        )