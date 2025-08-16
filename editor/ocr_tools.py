# -*- coding: utf-8 -*-
import pytesseract
from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox


class OCRManager:
    """Класс для управления OCR функциональностью"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._setup_tesseract()

    def _setup_tesseract(self):
        """Настроить путь к Tesseract если указан в конфигурации"""
        tpath = self.cfg.get("tesseract_path", "")
        if tpath:
            pytesseract.pytesseract.tesseract_cmd = tpath

    def extract_text_from_image(self, image: Image.Image) -> str:
        """Извлечь текст из изображения с помощью OCR"""
        try:
            text = pytesseract.image_to_string(image)
            return text or ""
        except Exception as e:
            raise OCRError(f"Ошибка OCR: {e}\n\nПроверьте установку Tesseract.")

    def ocr_to_clipboard(self, image: Image.Image, parent_widget=None) -> bool:
        """Распознать текст и скопировать в буфер обмена"""
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
                QMessageBox.warning(parent_widget, "OCR", f"Неожиданная ошибка: {e}", QMessageBox.Ok)
            return False


class OCRError(Exception):
    """Исключение для ошибок OCR"""
    pass
