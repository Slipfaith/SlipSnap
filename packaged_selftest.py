# -*- coding: utf-8 -*-
"""Release checks that must run inside the frozen SlipSnap executable."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication, QLineEdit

from api_key_store import get_api_key
from cloud_ocr import PROVIDER_NAMES, check_cloud_provider
from editor.editor_window import EditorWindow
from editor.ui.ocr_cloud_dialog import OcrCloudSettingsDialog


logger = logging.getLogger(__name__)


def run_ocr_self_test(app: QApplication) -> None:
    """Exercise lazy OCR UI, credential access, and provider connectivity."""
    icon_path = Path(__file__).resolve().with_name("SlipSnap.ico")
    if not icon_path.is_file():
        raise RuntimeError(f"Packaged application icon is missing: {icon_path}")
    file_icon = QIcon(str(icon_path))
    if file_icon.isNull() or len(file_icon.availableSizes()) < 3:
        raise RuntimeError("Packaged application icon is invalid or not multi-resolution")
    if app.windowIcon().isNull():
        raise RuntimeError("Qt application icon was not initialized")

    image = QImage(160, 80, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    window = EditorWindow(image, {})
    dialog = None
    try:
        dialog = OcrCloudSettingsDialog(window)
        for provider in PROVIDER_NAMES:
            editor = dialog.findChild(QLineEdit, f"{provider}ApiKeyEdit")
            if editor is None:
                raise RuntimeError(f"OCR settings editor is missing for {provider}")

        dialog.show()
        app.processEvents()
        if not dialog.isVisible():
            raise RuntimeError("OCR API settings dialog did not become visible")
        dialog.close()
        app.processEvents()

        for provider in PROVIDER_NAMES:
            key = get_api_key(provider)
            if not key:
                raise RuntimeError(
                    f"No saved API key is available for {PROVIDER_NAMES[provider]}"
                )
            check_cloud_provider(provider, key)
            logger.info("Packaged OCR provider check passed: %s", provider)
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        window.close()
        window.deleteLater()
        app.processEvents()
