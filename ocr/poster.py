"""Poster-specific OCR helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from pytesseract import Output


@dataclass
class OCRResult:
    text: str
    confidence: float
    area_ratio: float


def _prepare_image(image: Image.Image) -> Image.Image:
    """Improve contrast and grayscale to aid OCR."""

    if image.mode not in ("L", "LA"):
        image = image.convert("L")
    image = ImageOps.autocontrast(image)
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.5)
    return image


def _normalise(text: str) -> str:
    text = re.sub(r"[\s\n]+", " ", text)
    text = text.strip(" -\u2014")
    return text.strip()


class PosterOCR:
    """Detect prominent text from a movie poster image."""

    def __init__(self, languages: Iterable[str] | str = ("rus", "eng")) -> None:
        if isinstance(languages, str):
            self.languages = languages
        else:
            self.languages = "+".join(dict.fromkeys(languages))

    def extract_title(self, image: Image.Image) -> Optional[OCRResult]:
        """Return the most likely movie title text from *image*.

        The heuristic ranks recognised text lines by their area, confidence and
        length. ``None`` is returned if OCR produced no viable candidates.
        """

        if image.mode not in ("L", "RGB", "RGBA"):
            image = image.convert("RGB")

        prepared = _prepare_image(image)
        width, height = prepared.size
        img_area = max(1, width * height)

        try:
            data = pytesseract.image_to_data(
                prepared,
                lang=self.languages,
                output_type=Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(
                "Tesseract OCR не найден. Настройте путь через configure_local_tesseract()."
            ) from exc

        lines: Dict[Tuple[int, int, int, int], Dict[str, List[float]]] = {}
        n = len(data.get("text", []))
        for i in range(n):
            text = data["text"][i].strip()
            conf_raw = data.get("conf", ["0"][i])
            try:
                conf = float(conf_raw)
            except (ValueError, TypeError):
                conf = 0.0
            if not text or conf < 50:
                continue

            key = (
                data.get("page_num", [0])[i],
                data.get("block_num", [0])[i],
                data.get("par_num", [0])[i],
                data.get("line_num", [0])[i],
            )
            entry = lines.setdefault(
                key,
                {"text": [], "conf": [], "width": [], "height": []},
            )
            entry["text"].append(text)
            entry["conf"].append(conf)
            entry["width"].append(float(data.get("width", [0])[i] or 0))
            entry["height"].append(float(data.get("height", [0])[i] or 0))

        best: Optional[OCRResult] = None
        for entry in lines.values():
            joined = _normalise(" ".join(entry["text"]))
            if not joined:
                continue
            avg_conf = sum(entry["conf"]) / len(entry["conf"])
            max_width = max(entry["width"]) if entry["width"] else 0
            max_height = max(entry["height"]) if entry["height"] else 0
            area_ratio = (max_width * max_height) / img_area
            score = avg_conf + area_ratio * 400 + len(joined) * 1.5
            if best is None or score > (best.confidence + best.area_ratio * 400 + len(best.text) * 1.5):
                best = OCRResult(joined, avg_conf, area_ratio)

        return best


def extract_movie_title(image: Image.Image, languages: Iterable[str] | str = ("rus", "eng")) -> Optional[str]:
    """Convenience wrapper returning the detected movie title as plain text."""

    ocr = PosterOCR(languages)
    result = ocr.extract_title(image)
    return result.text if result else None


__all__ = ["PosterOCR", "extract_movie_title", "OCRResult"]
