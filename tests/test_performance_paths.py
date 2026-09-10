# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem, QGraphicsScene

from clipboard_utils import copy_pil_image_to_clipboard
from editor.tools.blur_tool import BlurTool, _preview_target_size
from editor.ui.high_quality_pixmap_item import HighQualityPixmapItem
from logic import save_history_png_async


class _BlurCanvasStub:
    def __init__(self, image: QImage):
        self.scene = QGraphicsScene()
        base = QGraphicsPixmapItem(QPixmap.fromImage(image))
        base.setData(0, "screenshot")
        self.scene.addItem(base)


class PerformancePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_clipboard_capture_returns_direct_qimage_and_encoded_png(self) -> None:
        image = Image.new("RGBA", (32, 24), (12, 34, 56, 255))

        with patch("clipboard_utils._copy_png_and_dibv5_win32", return_value=True):
            qimg, png_data = copy_pil_image_to_clipboard(
                image,
                return_png_data=True,
            )

        self.assertEqual(qimg.size(), QImage.fromData(png_data, "PNG").size())
        self.assertEqual(qimg.pixelColor(10, 10), QColor(12, 34, 56, 255))
        self.assertTrue(png_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_history_can_reuse_clipboard_png_in_background(self) -> None:
        image = Image.new("RGBA", (20, 16), (90, 80, 70, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        with tempfile.TemporaryDirectory(prefix="slipsnap_history_test_") as tmp:
            with patch("logic.HISTORY_DIR", Path(tmp)):
                saved = save_history_png_async(buffer.getvalue()).result(timeout=3)

            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_bytes(), buffer.getvalue())

    def test_pixmap_scaling_keeps_original_raster(self) -> None:
        image = QImage(160, 90, QImage.Format_ARGB32)
        image.fill(QColor("blue"))
        item = HighQualityPixmapItem(image)

        item.setScale(3.5)

        self.assertEqual(item.pixmap().size(), image.size())
        self.assertAlmostEqual(item.scale(), 3.5)
        self.assertAlmostEqual(item.sceneBoundingRect().width(), 560.0)
        self.assertAlmostEqual(item.sceneBoundingRect().height(), 315.0)

    def test_blur_preview_is_downscaled_and_rate_limited(self) -> None:
        image = QImage(1400, 800, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        canvas = _BlurCanvasStub(image)
        tool = BlurTool(canvas, QColor("blue"))
        preview = QPixmap(480, 274)
        preview.fill(QColor("blue"))

        with patch(
            "editor.tools.blur_tool._generate_blur_pixmap",
            return_value=(preview, QPointF(0, 0)),
        ) as generate:
            tool.press(QPointF(0, 0))
            tool.move(QPointF(1400, 800))
            tool.move(QPointF(1300, 700))

        self.assertEqual(generate.call_count, 1)
        target_size = generate.call_args.kwargs["target_size"]
        self.assertLessEqual(max(target_size.width(), target_size.height()), 480)
        self.assertGreater(tool._preview_item.scale(), 1.0)

    def test_blur_preview_size_preserves_aspect_ratio(self) -> None:
        size = _preview_target_size(QRectF(0, 0, 1400, 800))

        self.assertEqual(size.width(), 480)
        self.assertAlmostEqual(size.height() / size.width(), 800 / 1400, places=2)


if __name__ == "__main__":
    unittest.main()
