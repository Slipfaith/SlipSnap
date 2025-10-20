"""Utilities for running OCR locally via Tesseract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Sequence, Tuple, Union

from PIL import Image


class _OcrEngine(Protocol):
    """Protocol for objects that expose pytesseract's interface."""

    class Output(Protocol):  # type: ignore[override]
        DICT: int  # pragma: no cover - attribute only used for typing

    Output: Output

    def image_to_data(  # pragma: no cover - covered through integration tests
        self, image: Image.Image, lang: str, output_type: int
    ) -> dict:
        ...


@dataclass
class OCRWord:
    """Single OCR result piece with its confidence and bounding box."""

    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]


class LocalOCRClient:
    """Client that runs OCR using the local Tesseract installation."""

    def __init__(
        self,
        lang: str = "rus+eng",
        *,
        min_confidence: float = 0.0,
        ocr_engine: Optional[_OcrEngine] = None,
    ) -> None:
        if ocr_engine is None:
            try:
                import pytesseract  # type: ignore
            except Exception as exc:  # pragma: no cover - import error path
                raise RuntimeError("pytesseract is required for LocalOCRClient") from exc
            ocr_engine = pytesseract

        self._lang = lang
        self._min_confidence = float(min_confidence)
        self._ocr = ocr_engine

    def recognize(self, image: Image.Image) -> str:
        """Return recognized text from ``image``."""

        data = self._ocr.image_to_data(
            image, lang=self._lang, output_type=self._ocr.Output.DICT
        )
        words = [word.text for word in self._iter_words(data)]
        return " ".join(words).strip()

    def _iter_words(self, data: dict) -> Iterable[OCRWord]:
        texts: Sequence[str] = data.get("text", [])
        confs: Sequence[Union[str, float, int, None]] = data.get("conf", [])

        left = data.get("left", [])
        top = data.get("top", [])
        width = data.get("width", [])
        height = data.get("height", [])

        size = min(len(texts), len(confs), len(left), len(top), len(width), len(height))
        for idx in range(size):
            text = (texts[idx] or "").strip()
            if not text:
                continue

            confidence = _parse_confidence(confs[idx])
            if confidence is None or confidence < self._min_confidence:
                continue

            bbox = (
                int(left[idx]) if idx < len(left) else 0,
                int(top[idx]) if idx < len(top) else 0,
                int(width[idx]) if idx < len(width) else 0,
                int(height[idx]) if idx < len(height) else 0,
            )
            yield OCRWord(text=text, confidence=confidence, bbox=bbox)


def _parse_confidence(value: Union[str, float, int, None]) -> Optional[float]:
    """Safely parse the confidence returned by pytesseract."""

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None
