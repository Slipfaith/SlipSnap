"""OCR utilities for SlipSnap."""

from .recognizer import (
    OcrEngine,
    OcrError,
    OcrUnavailableError,
    OcrSpan,
)

__all__ = [
    "OcrEngine",
    "OcrError",
    "OcrUnavailableError",
    "OcrSpan",
]
