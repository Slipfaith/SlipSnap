from __future__ import annotations

import json
import unittest
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

from clipboard_utils import SLIPSNAP_MEME_MIME
from editor.image_utils import gif_bytes_from_mime, gif_paths_from_mime


_FIXTURE_GIF = Path(__file__).resolve().parent / "fixtures" / "sample.gif"


class GifMimeParsingTests(unittest.TestCase):
    def test_gif_paths_from_slipsnap_custom_mime(self) -> None:
        mime = QMimeData()
        payload = {"kind": "gif", "path": str(_FIXTURE_GIF)}
        mime.setData(SLIPSNAP_MEME_MIME, json.dumps(payload).encode("utf-8"))

        paths = gif_paths_from_mime(mime)
        self.assertEqual(paths, [_FIXTURE_GIF])

    def test_gif_paths_from_urls_deduplicate(self) -> None:
        mime = QMimeData()
        mime.setUrls(
            [
                QUrl.fromLocalFile(str(_FIXTURE_GIF)),
                QUrl.fromLocalFile(str(_FIXTURE_GIF)),
            ]
        )

        paths = gif_paths_from_mime(mime)
        self.assertEqual(paths, [_FIXTURE_GIF])

    def test_gif_paths_from_custom_mime_ignores_missing_file(self) -> None:
        missing = _FIXTURE_GIF.parent / "missing.gif"
        mime = QMimeData()
        payload = {"kind": "gif", "path": str(missing)}
        mime.setData(SLIPSNAP_MEME_MIME, json.dumps(payload).encode("utf-8"))

        self.assertEqual(gif_paths_from_mime(mime), [])

    def test_gif_bytes_from_image_gif_payload(self) -> None:
        gif_data = b"GIF89a\x00\x00\x00\x00"
        mime = QMimeData()
        mime.setData("image/gif", gif_data)

        self.assertEqual(gif_bytes_from_mime(mime), gif_data)

    def test_gif_bytes_from_mime_rejects_non_gif_payload(self) -> None:
        mime = QMimeData()
        mime.setData("image/gif", b"NOT_GIF_DATA")

        self.assertIsNone(gif_bytes_from_mime(mime))


if __name__ == "__main__":
    unittest.main()
