"""OCR utilities for SlipSnap."""

from .local import configure_local_tesseract
from .poster import OCRResult, PosterOCR, extract_movie_title

__all__ = [
    "configure_local_tesseract",
    "OCRResult",
    "PosterOCR",
    "extract_movie_title",
]
