"""Utility helpers for managing the local meme stash."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from PIL import Image

from logic import MEME_DIR

try:  # Pillow >= 9.1.0
    _RESAMPLE = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - fallback for older Pillow
    _RESAMPLE = Image.LANCZOS  # type: ignore[attr-defined]

MAX_MEME_SIZE = 512


def ensure_meme_dir() -> Path:
    """Ensure the meme directory exists and return it."""

    MEME_DIR.mkdir(parents=True, exist_ok=True)
    return MEME_DIR


def _normalize_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    allowed = "-_"
    cleaned = [ch.lower() for ch in name if ch.isalnum() or ch in allowed]
    base = "".join(cleaned).strip("._-")
    return base or None


def _prepare_image(image: Image.Image) -> Image.Image:
    """Convert image to RGBA and limit its size to MAX_MEME_SIZE."""

    if image.mode not in ("RGBA", "LA"):
        image = image.convert("RGBA")
    else:
        image = image.copy()

    width, height = image.size
    max_dim = max(width, height)
    if max_dim > MAX_MEME_SIZE and max_dim > 0:
        scale = MAX_MEME_SIZE / float(max_dim)
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        image = image.resize(new_size, _RESAMPLE)
    return image


def save_meme_image(image: Image.Image, *, stem: Optional[str] = None) -> Path:
    """Save ``image`` into the meme directory, ensuring constraints."""

    ensure_meme_dir()
    prepared = _prepare_image(image)

    base_name = _normalize_name(stem) or f"meme_{uuid.uuid4().hex}"
    candidate = MEME_DIR / f"{base_name}.png"
    counter = 1
    while candidate.exists():
        candidate = MEME_DIR / f"{base_name}_{counter}.png"
        counter += 1

    prepared.save(candidate, format="PNG")
    return candidate


def add_memes_from_paths(paths: Iterable[Path]) -> List[Path]:
    """Import memes from file paths and return saved paths."""

    saved: List[Path] = []
    for path in paths:
        try:
            with Image.open(path) as img:
                saved.append(save_meme_image(img, stem=path.stem))
        except Exception as exc:
            raise RuntimeError(f"Не удалось добавить мем из файла '{path}': {exc}") from exc
    return saved


def list_memes() -> List[Path]:
    """Return meme files sorted by modification time (newest first)."""

    ensure_meme_dir()
    files = sorted(MEME_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def delete_memes(paths: Iterable[Path]) -> None:
    """Remove provided meme files from the stash."""

    for path in paths:
        if path.parent != MEME_DIR:
            continue
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

