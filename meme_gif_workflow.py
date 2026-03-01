# -*- coding: utf-8 -*-
"""Workflow helpers for storing recorded GIFs in meme library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from meme_library import save_meme_gif


@dataclass(frozen=True)
class GifLibrarySaveResult:
    ok: bool
    target_path: Optional[Path] = None
    error: str = ""


def add_gif_to_meme_library(source_gif: Path, *, stem: Optional[str] = None) -> Path:
    """Validate and copy a GIF into meme library."""

    source = Path(source_gif)
    if not source.exists():
        raise RuntimeError(f"GIF файл не найден: {source}")
    if source.suffix.lower() != ".gif":
        raise RuntimeError("В библиотеку мемов по этому сценарию можно добавлять только GIF.")

    try:
        with Image.open(source) as img:
            if str(getattr(img, "format", "")).upper() != "GIF":
                raise RuntimeError("Файл имеет расширение .gif, но не является GIF.")
    except Exception as exc:
        raise RuntimeError(f"Не удалось проверить GIF: {exc}") from exc

    return save_meme_gif(source, stem=stem or source.stem)


def try_add_gif_to_meme_library(source_gif: Path, *, stem: Optional[str] = None) -> GifLibrarySaveResult:
    """Safe wrapper for UI flows that should not crash on import failure."""

    try:
        saved = add_gif_to_meme_library(source_gif, stem=stem)
        return GifLibrarySaveResult(ok=True, target_path=saved)
    except Exception as exc:
        return GifLibrarySaveResult(ok=False, error=str(exc))
