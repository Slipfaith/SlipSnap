from __future__ import annotations

import json
from pathlib import Path
from typing import List

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QPixmap

from clipboard_utils import SLIPSNAP_MEME_MIME


def _convert_to_qimage(data) -> QImage | None:
    """Try to convert clipboard/drag payload to QImage."""
    if isinstance(data, QImage):
        return data
    if isinstance(data, QPixmap):
        return data.toImage()
    # Some platforms return QVariant wrappers that have toImage
    convert = getattr(data, "toImage", None)
    if callable(convert):
        return convert()
    return None


def _looks_like_gif(data: bytes) -> bool:
    return data.startswith(b"GIF87a") or data.startswith(b"GIF89a")


def _append_unique_path(paths: List[Path], candidate: Path, seen: set[str]) -> None:
    try:
        key = str(candidate.resolve())
    except Exception:
        key = str(candidate)
    if key in seen:
        return
    seen.add(key)
    paths.append(candidate)


def gif_paths_from_mime(mime: QMimeData | None) -> List[Path]:
    """Extract local GIF paths from custom SlipSnap mime and URL payloads."""

    paths: List[Path] = []
    seen: set[str] = set()
    if mime is None:
        return paths

    if mime.hasFormat(SLIPSNAP_MEME_MIME):
        try:
            payload_raw = bytes(mime.data(SLIPSNAP_MEME_MIME))
            payload = json.loads(payload_raw.decode("utf-8"))
            if isinstance(payload, dict) and payload.get("kind") == "gif":
                path_value = payload.get("path")
                if path_value:
                    candidate = Path(str(path_value))
                    if candidate.is_file() and candidate.suffix.lower() == ".gif":
                        _append_unique_path(paths, candidate, seen)
        except Exception:
            pass

    if mime.hasUrls():
        for url in mime.urls():
            if not isinstance(url, QUrl) or not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            if candidate.is_file() and candidate.suffix.lower() == ".gif":
                _append_unique_path(paths, candidate, seen)

    return paths


def gif_bytes_from_mime(mime: QMimeData | None) -> bytes | None:
    """Extract raw GIF bytes from mime payload when available."""

    if mime is None:
        return None
    if not mime.hasFormat("image/gif"):
        return None
    data = bytes(mime.data("image/gif"))
    if not data:
        return None
    if _looks_like_gif(data):
        return data
    return None


def images_from_mime(mime: QMimeData | None) -> List[QImage]:
    """Extract QImages contained in mime data."""
    images: List[QImage] = []
    if mime is None:
        return images

    if mime.hasImage():
        qimg = _convert_to_qimage(mime.imageData())
        if qimg is not None and not qimg.isNull():
            images.append(qimg)

    if mime.hasUrls():
        for url in mime.urls():
            if isinstance(url, QUrl) and url.isLocalFile():
                local_path = url.toLocalFile()
                qimg = QImage(local_path)
                if not qimg.isNull():
                    images.append(qimg)

    return images
