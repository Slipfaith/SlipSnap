# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage

from editor.image_utils import images_from_mime


_FIXTURE_PNG = Path(__file__).resolve().parent / "fixtures" / "static.png"


class ImageMimeParsingTests(unittest.TestCase):
    def test_images_from_qimage_payload(self) -> None:
        src = QImage(12, 9, QImage.Format_ARGB32)
        src.fill(0xFF00FF00)
        mime = QMimeData()
        mime.setImageData(src)

        images = images_from_mime(mime)
        self.assertEqual(len(images), 1)
        self.assertFalse(images[0].isNull())
        self.assertEqual(images[0].width(), 12)
        self.assertEqual(images[0].height(), 9)

    def test_images_from_local_png_url(self) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(_FIXTURE_PNG))])

        images = images_from_mime(mime)
        self.assertEqual(len(images), 1)
        self.assertFalse(images[0].isNull())
        self.assertEqual(images[0].width(), 8)
        self.assertEqual(images[0].height(), 6)


if __name__ == "__main__":
    unittest.main()