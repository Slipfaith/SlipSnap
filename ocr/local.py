"""Helpers for configuring a local Tesseract installation."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

import pytesseract


_DEFAULT_CANDIDATES: tuple[str, ...] = (
    r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def _resolve_executable(path_like: os.PathLike[str] | str) -> Optional[Path]:
    """Return the executable path if it exists.

    The helper accepts either a direct path to the binary or a directory that
    contains the binary.
    """

    candidate = Path(path_like).expanduser()
    if candidate.is_dir():
        for name in ("tesseract.exe", "tesseract"):
            exec_path = candidate / name
            if exec_path.exists() and os.access(exec_path, os.X_OK):
                return exec_path
        return None
    if candidate.exists() and os.access(candidate, os.X_OK):
        return candidate
    return None


def configure_local_tesseract(executable: Optional[str] = None, *, search: bool = True) -> Optional[Path]:
    """Configure :mod:`pytesseract` to use a locally installed Tesseract binary.

    Parameters
    ----------
    executable:
        Explicit path to the Tesseract executable or to a directory that
        contains it.
    search:
        When ``True`` (default) and *executable* is not provided, typical
        installation paths along with the current ``PATH`` are scanned.

    Returns
    -------
    Optional[Path]
        Path to the detected Tesseract executable, or ``None`` if nothing was
        found. When a path is returned, :mod:`pytesseract` is configured to use
        it immediately.
    """

    if executable:
        resolved = _resolve_executable(executable)
        if not resolved:
            raise FileNotFoundError(f"Не удалось найти Tesseract по пути: {executable}")
        pytesseract.pytesseract.tesseract_cmd = str(resolved)
        return resolved

    if search:
        # Check PATH first
        which_path = shutil.which("tesseract")
        if which_path:
            resolved = _resolve_executable(which_path)
            if resolved:
                pytesseract.pytesseract.tesseract_cmd = str(resolved)
                return resolved

        for candidate in _DEFAULT_CANDIDATES:
            resolved = _resolve_executable(candidate)
            if resolved:
                pytesseract.pytesseract.tesseract_cmd = str(resolved)
                return resolved

    return None


__all__ = ["configure_local_tesseract"]
