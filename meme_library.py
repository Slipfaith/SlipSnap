"""Utility helpers for managing the local meme stash."""

from __future__ import annotations

import shutil
import time
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
STATIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MEME_EXTENSIONS = STATIC_IMAGE_EXTENSIONS | {".gif"}


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


def _unique_target(stem: str, extension: str) -> Path:
    normalized_ext = extension if extension.startswith(".") else f".{extension}"
    candidate = MEME_DIR / f"{stem}{normalized_ext}"
    counter = 1
    while candidate.exists():
        candidate = MEME_DIR / f"{stem}_{counter}{normalized_ext}"
        counter += 1
    return candidate


def save_meme_image(image: Image.Image, *, stem: Optional[str] = None) -> Path:
    """Save ``image`` into the meme directory, ensuring constraints."""

    ensure_meme_dir()
    prepared = _prepare_image(image)

    base_name = _normalize_name(stem) or f"meme_{uuid.uuid4().hex}"
    candidate = _unique_target(base_name, ".png")

    prepared.save(candidate, format="PNG")
    return candidate


def save_meme_gif(path: Path, *, stem: Optional[str] = None) -> Path:
    """Copy GIF to meme library without re-encoding to keep animation."""

    ensure_meme_dir()
    source = Path(path)
    if not source.exists():
        raise RuntimeError(f"GIF файл не найден: {source}")
    if source.suffix.lower() != ".gif":
        raise RuntimeError(f"Ожидался GIF файл, получено: {source.suffix}")

    # Validate that file is an actual GIF before copying.
    try:
        with Image.open(source) as img:
            if str(getattr(img, "format", "")).upper() != "GIF":
                raise RuntimeError("Файл имеет расширение .gif, но формат не GIF.")
    except Exception as exc:
        raise RuntimeError(f"Не удалось прочитать GIF '{source}': {exc}") from exc

    base_name = _normalize_name(stem) or f"meme_{uuid.uuid4().hex}"
    candidate = _unique_target(base_name, ".gif")
    try:
        shutil.copy2(source, candidate)
    except Exception as exc:
        raise RuntimeError(f"Не удалось сохранить GIF в библиотеку: {exc}") from exc
    return candidate


def add_memes_from_paths(paths: Iterable[Path]) -> List[Path]:
    """Import memes from file paths and return saved paths."""

    saved: List[Path] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".gif":
            try:
                saved.append(save_meme_gif(path, stem=path.stem))
            except Exception as exc:
                raise RuntimeError(f"Не удалось добавить GIF '{path}': {exc}") from exc
            continue
        if suffix not in STATIC_IMAGE_EXTENSIONS:
            raise RuntimeError(f"Неподдерживаемый формат файла: '{path.suffix}'")
        try:
            with Image.open(path) as img:
                saved.append(save_meme_image(img, stem=path.stem))
        except Exception as exc:
            raise RuntimeError(f"Не удалось добавить мем из файла '{path}': {exc}") from exc
    return saved


def list_memes() -> List[Path]:
    """Return meme files sorted by modification time (newest first)."""

    ensure_meme_dir()
    files = sorted(
        [p for p in MEME_DIR.iterdir() if p.is_file() and p.suffix.lower() in MEME_EXTENSIONS],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def delete_memes(paths: Iterable[Path]) -> None:
    """Remove provided meme files from the stash."""

    try:
        meme_dir_resolved = MEME_DIR.resolve()
    except Exception:
        meme_dir_resolved = MEME_DIR

    for path in paths:
        candidate = Path(path)
        try:
            parent_resolved = candidate.resolve().parent
        except Exception:
            parent_resolved = candidate.parent
        if parent_resolved != meme_dir_resolved and candidate.parent != MEME_DIR:
            continue
        for attempt in range(3):
            try:
                candidate.unlink(missing_ok=True)
                break
            except PermissionError:
                if attempt >= 2:
                    break
                time.sleep(0.04)
            except Exception:
                break
