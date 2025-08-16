# -*- coding: utf-8 -*-
# editor/ocr_tools.py — OCR «под ключ»: Tesseract + pytesseract
from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from typing import Optional, List, Any, Dict

import pytesseract
from PIL import Image, ImageOps, ImageFilter
from PySide6.QtWidgets import QApplication, QMessageBox


class OCRError(Exception):
    """Исключение для ошибок OCR."""
    pass


@dataclass
class _Params:
    lang: str = "eng+rus"          # мульти-язык по умолчанию
    psm: int = 6                   # единый блок текста
    oem: Optional[int] = None      # авто
    dpi: Optional[int] = 300       # подсказка DPI
    whitelist: Optional[str] = None


class OCRManager:
    """Класс для управления OCR (используется EditorWindow.ocr_current и LiveText)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.params = _Params(
            lang=str(self.cfg.get("ocr_lang", "eng+rus")),
            psm=self._to_int(self.cfg.get("ocr_psm"), 6),
            oem=self._to_opt_int(self.cfg.get("ocr_oem")),
            dpi=self._to_opt_int(self.cfg.get("ocr_dpi"), default=300),
            whitelist=(self.cfg.get("ocr_whitelist") or None),
        )
        self._tesseract_ok = False
        self._tesseract_path = ""
        self._setup_tesseract()

    # ---------- публичный API ----------
    def extract_text_from_image(self, image: Image.Image) -> str:
        """Распознать текст из PIL.Image → str."""
        self._check_ready()
        im = self._preprocess(image)
        config = self._build_config()
        try:
            txt = pytesseract.image_to_string(im, lang=self.params.lang, config=config)
            return (txt or "").strip()
        except Exception as e:
            raise OCRError(self._help_msg(str(e)))

    def image_to_data(self, image: Image.Image) -> Dict[str, List]:
        """Вернуть словарь с боксами (image_to_data) для Live Text."""
        self._check_ready()
        im = self._preprocess(image)
        config = self._build_config()
        try:
            return pytesseract.image_to_data(
                im, lang=self.params.lang, config=config, output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            raise OCRError(self._help_msg(str(e)))

    def ocr_to_clipboard(self, image: Image.Image, parent_widget=None) -> bool:
        """Распознать и положить текст в буфер обмена."""
        try:
            text = self.extract_text_from_image(image)
            QApplication.clipboard().setText(text)
            return True
        except OCRError as e:
            if parent_widget:
                QMessageBox.warning(parent_widget, "OCR", str(e), QMessageBox.Ok)
            return False
        except Exception as e:
            if parent_widget:
                QMessageBox.warning(parent_widget, "OCR", f"Неожиданная ошибка OCR: {e}", QMessageBox.Ok)
            return False

    # ---------- настройка Tesseract ----------
    def _setup_tesseract(self) -> None:
        tpath = (self.cfg.get("tesseract_path") or os.environ.get("TESSERACT_PATH", "")).strip()
        if not tpath:
            tpath = self._autodetect_tesseract() or ""

        if not tpath or not os.path.isfile(tpath):
            self._tesseract_ok = False
            self._tesseract_path = tpath
            return

        pytesseract.pytesseract.tesseract_cmd = tpath
        self._tesseract_ok = True
        self._tesseract_path = tpath

        # В PATH директорию бинарника (нужно на Windows для DLL)
        bin_dir = os.path.dirname(tpath)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

        # Если рядом есть tessdata — подскажем TESSDATA_PREFIX
        td = os.path.join(bin_dir, "tessdata")
        if os.path.isdir(td) and not os.environ.get("TESSDATA_PREFIX"):
            os.environ["TESSDATA_PREFIX"] = td

    def _autodetect_tesseract(self) -> Optional[str]:
        p = shutil.which("tesseract")
        if p and os.path.isfile(p):
            return p
        sysname = platform.system().lower()
        if sysname.startswith("win"):
            for c in (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ):
                if os.path.isfile(c):
                    return c
        else:
            for c in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract", "/bin/tesseract"):
                if os.path.isfile(c):
                    return c
        return None

    # ---------- утилиты ----------
    @staticmethod
    def _to_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _to_opt_int(v: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(v) if v is not None and str(v).strip() != "" else default
        except Exception:
            return default

    def _check_ready(self) -> None:
        if not self._tesseract_ok:
            raise OCRError(self._help_msg("Tesseract не найден"))

    def _build_config(self) -> str:
        opts: List[str] = []
        if self.params.oem is not None:
            opts += ["--oem", str(self.params.oem)]
        opts += ["--psm", str(self.params.psm)]
        if self.params.dpi:
            opts += ["-c", f"user_defined_dpi={self.params.dpi}"]
        if self.params.whitelist:
            opts += ["-c", f"tessedit_char_whitelist={self.params.whitelist}"]
        return " ".join(opts)

    @staticmethod
    def _preprocess(img: Image.Image) -> Image.Image:
        """Мягкая подготовка: автоконтраст + лёгкая резкость."""
        try:
            if img.mode in ("RGBA", "LA"):
                bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                bg.alpha_composite(img)
                img = bg.convert("RGB")
            im = img.convert("L")
            im = ImageOps.autocontrast(im, cutoff=1)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=3))
            return im
        except Exception:
            return img

    def _help_msg(self, err: str) -> str:
        msg = (
            f"{err}\n\n"
            "Что сделать:\n"
            "1) Установить Tesseract (Windows: C:\\Program Files\\Tesseract-OCR\\tesseract.exe).\n"
            "2) Прописать путь в конфиге (~/.screenshot_config.json) ключом \"tesseract_path\"\n"
            "   или добавить папку в PATH / задать TESSERACT_PATH.\n"
        )
        if self._tesseract_path:
            msg += f"\nТекущий путь: {self._tesseract_path}"
        return msg
