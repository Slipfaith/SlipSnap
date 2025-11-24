from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image
from PySide6.QtGui import QImage
import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError

from logic import qimage_to_pil


class OcrError(RuntimeError):
    """User-facing OCR errors with actionable messaging."""


@dataclass
class OcrResult:
    text: str
    language_tag: str
    missing_languages: List[str] = field(default_factory=list)
    fallback_used: bool = False
    warnings: List[str] = field(default_factory=list)
    languages_used: List[str] = field(default_factory=list)


@dataclass
class OcrSettings:
    preferred_languages: List[str] = field(default_factory=lambda: ["eng"])
    last_language: str = "auto"

    @classmethod
    def from_config(cls, cfg: dict) -> "OcrSettings":
        data = cfg.get("ocr_settings") if isinstance(cfg, dict) else None
        if not isinstance(data, dict):
            data = {}
        preferred = data.get("preferred_languages")
        if not isinstance(preferred, list):
            preferred = ["eng"]
        preferred = [str(lang).strip() for lang in preferred if str(lang).strip()]
        if not preferred:
            preferred = ["eng"]
        last_language = data.get("last_language", "auto")
        if not isinstance(last_language, str) or not last_language.strip():
            last_language = "auto"
        return cls(preferred_languages=preferred, last_language=last_language)

    def to_dict(self) -> dict:
        return {
            "preferred_languages": list(self.preferred_languages),
            "last_language": self.last_language,
        }

    def remember_run(self, requested: str, languages_used: Sequence[str]) -> None:
        if requested:
            self.last_language = requested
        used = [str(lang).strip() for lang in languages_used if str(lang).strip()]
        if used:
            # Preserve order while removing duplicates
            seen = set()
            ordered = []
            for lang in used:
                if lang not in seen:
                    ordered.append(lang)
                    seen.add(lang)
            self.preferred_languages = ordered


LangHint = Optional[Union[str, Sequence[str]]]


def _ensure_pil_image(image: Union[Image.Image, QImage]) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, QImage):
        return qimage_to_pil(image)
    raise OcrError("Передано неподдерживаемое изображение для OCR")


def _normalize_languages(language_hint: LangHint, settings: OcrSettings, available: Sequence[str]) -> Tuple[Optional[str], List[str], List[str]]:
    if isinstance(language_hint, str):
        hint = language_hint.strip()
        if not hint or hint.lower() == "auto":
            parsed = []
        else:
            parsed = [part.strip() for part in hint.replace(",", "+").split("+") if part.strip()]
    elif isinstance(language_hint, (list, tuple, set)):
        parsed = [str(lang).strip() for lang in language_hint if str(lang).strip()]
    else:
        parsed = []

    if not parsed:
        parsed = list(settings.preferred_languages)

    normalized = []
    seen = set()
    for lang in parsed:
        if lang and lang not in seen:
            normalized.append(lang)
            seen.add(lang)

    missing = [lang for lang in normalized if available and lang not in available]
    usable = [lang for lang in normalized if not available or lang in available]
    lang_string = "+".join(usable) if usable else None
    return lang_string, missing, usable


def get_available_languages() -> List[str]:
    try:
        return pytesseract.get_languages(config="")
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Установите бинарник tesseract-ocr и добавьте его в PATH."
        ) from exc
    except TesseractError:
        # Tesseract is present but cannot list languages (keep working with fallback)
        return []


def run_ocr(image: Union[Image.Image, QImage], settings: OcrSettings, language_hint: LangHint = None) -> OcrResult:
    pil_image = _ensure_pil_image(image)
    available = get_available_languages()
    lang_string, missing, usable_langs = _normalize_languages(language_hint, settings, available)

    try:
        # Explicit check so we can present a friendly error before attempting OCR
        pytesseract.get_tesseract_version()
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Установите tesseract-ocr и перезапустите приложение."
        ) from exc

    def _perform(lang_value: Optional[str]) -> str:
        return pytesseract.image_to_string(pil_image, lang=lang_value or None)

    warnings: List[str] = []
    try:
        text = _perform(lang_string)
        language_tag = lang_string or "auto"
    except TesseractError as exc:
        if missing:
            try:
                text = _perform(None)
                warnings.append(
                    "Отсутствуют языковые пакеты: "
                    + ", ".join(missing)
                    + ". Использовано автоопределение."
                )
                language_tag = "auto"
            except Exception:
                raise OcrError(
                    "Не хватает языковых данных Tesseract. Установите: " + ", ".join(missing)
                ) from exc
        else:
            raise OcrError(f"Ошибка OCR: {exc}") from exc

    return OcrResult(
        text=text.strip(),
        language_tag=language_tag,
        missing_languages=missing,
        fallback_used=language_tag == "auto" and bool(missing),
        warnings=warnings,
        languages_used=usable_langs,
    )
