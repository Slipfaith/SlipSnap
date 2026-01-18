from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image
from PySide6.QtGui import QImage

import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError

from logic import qimage_to_pil

# === Fallback поиск Tesseract (добавлено) ===
import os
import threading

_FALLBACK_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

for _p in _FALLBACK_PATHS:
    if os.path.exists(_p):
        pytesseract.pytesseract.tesseract_cmd = _p
        break
# === конец добавленного кода ===


# На Windows скрываем всплывающие консольные окна Tesseract
if os.name == "nt":
    import subprocess

    _existing_kwargs = getattr(pytesseract.pytesseract, "popen_kwargs", {})
    _popen_kwargs = dict(_existing_kwargs) if isinstance(_existing_kwargs, dict) else {}

    # Блокируем создание консольного окна даже на доли секунды.
    # combination of CREATE_NO_WINDOW + скрытый STARTUPINFO помогает
    # и при установке tesseract_cmd пользователем.
    _popen_kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    if "startupinfo" not in _popen_kwargs:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        _popen_kwargs["startupinfo"] = startup

    pytesseract.pytesseract.popen_kwargs = _popen_kwargs

    # Дополнительно патчим subprocess.Popen, чтобы любые внутренние вызовы
    # (включая subprocess.run) Tesseract не всплывали отдельным окном.
_AVAILABLE_LANG_CACHE: Optional[List[str]] = None
_WARMUP_LOCK = threading.Lock()
_WARMUP_STARTED = False


LANGUAGE_DISPLAY_NAMES = {
    "eng": "English",
    "rus": "Russian",
    "deu": "German",
    "fra": "French",
    "spa": "Spanish",
    "ita": "Italian",
    "por": "Portuguese",
    "ukr": "Ukrainian",
    "pol": "Polish",
    "nld": "Dutch",
    "tur": "Turkish",
    "ara": "Arabic",
    "heb": "Hebrew",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
}


def get_language_display_name(code: str) -> str:
    normalized = str(code).strip()
    if not normalized:
        return ""
    return LANGUAGE_DISPLAY_NAMES.get(normalized, normalized)


class OcrError(RuntimeError):
    """User-facing OCR errors with actionable messaging."""


@dataclass
class OcrWord:
    text: str
    bbox: Tuple[int, int, int, int]
    line_id: Tuple[int, int, int]


@dataclass
class OcrResult:
    text: str
    language_tag: str
    missing_languages: List[str] = field(default_factory=list)
    fallback_used: bool = False
    warnings: List[str] = field(default_factory=list)
    languages_used: List[str] = field(default_factory=list)
    words: List[OcrWord] = field(default_factory=list)


@dataclass
class OcrSettings:
    preferred_languages: List[str] = field(default_factory=lambda: ["eng"])
    last_language: str = "auto"
    auto_config: bool = True
    psm: Optional[int] = None
    oem: Optional[int] = None

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
        auto_config = data.get("auto_config", True)
        if not isinstance(auto_config, bool):
            auto_config = True
        psm = data.get("psm")
        if not isinstance(psm, int):
            psm = None
        oem = data.get("oem")
        if not isinstance(oem, int):
            oem = None
        return cls(
            preferred_languages=preferred,
            last_language=last_language,
            auto_config=auto_config,
            psm=psm,
            oem=oem,
        )

    def to_dict(self) -> dict:
        return {
            "preferred_languages": list(self.preferred_languages),
            "last_language": self.last_language,
            "auto_config": self.auto_config,
            "psm": self.psm,
            "oem": self.oem,
        }

    def remember_run(self, requested: str, languages_used: Sequence[str]) -> None:
        if requested:
            self.last_language = requested
        used = [str(lang).strip() for lang in languages_used if str(lang).strip()]
        if used:
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


def _build_tesseract_config(psm: Optional[int], oem: Optional[int]) -> str:
    parts: List[str] = []
    if psm is not None:
        parts.extend(["--psm", str(psm)])
    if oem is not None:
        parts.extend(["--oem", str(oem)])
    return " ".join(parts)


def _score_ocr_data(data: dict) -> float:
    try:
        confs = data.get("conf", [])
    except AttributeError:
        return 0.0
    numeric_confs = []
    for raw in confs:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            numeric_confs.append(value)
    if not numeric_confs:
        return 0.0
    avg_conf = sum(numeric_confs) / len(numeric_confs)
    word_count = sum(1 for raw in data.get("text", []) if str(raw).strip())
    return avg_conf + min(20.0, word_count * 0.2)


def _select_best_config(
    pil_image: Image.Image,
    lang_value: Optional[str],
    settings: OcrSettings,
) -> Tuple[str, Optional[dict]]:
    if not settings.auto_config:
        config = _build_tesseract_config(settings.psm, settings.oem)
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang_value or None,
                config=config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            data = None
        return config, data

    candidates = [
        (3, 3),
        (6, 3),
        (7, 3),
        (11, 3),
    ]
    best_config = ""
    best_data = None
    best_score = -1.0
    for psm, oem in candidates:
        config = _build_tesseract_config(psm, oem)
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang_value or None,
                config=config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            continue
        score = _score_ocr_data(data)
        if score > best_score:
            best_score = score
            best_config = config
            best_data = data
    if best_score < 0:
        return "", None
    return best_config, best_data


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
    global _AVAILABLE_LANG_CACHE
    if _AVAILABLE_LANG_CACHE is not None:
        return list(_AVAILABLE_LANG_CACHE)

    try:
        langs = pytesseract.get_languages(config="")
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Установите бинарник tesseract-ocr и добавьте его в PATH."
        ) from exc
    except TesseractError:
        langs = []

    _AVAILABLE_LANG_CACHE = list(langs)
    return list(_AVAILABLE_LANG_CACHE)


def warm_up_ocr(async_run: bool = True) -> None:
    """Preload Tesseract binaries and language list to avoid first-use lag."""

    def _warm() -> None:
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return
        try:
            get_available_languages()
        except Exception:
            pass

    global _WARMUP_STARTED
    with _WARMUP_LOCK:
        if _WARMUP_STARTED:
            return
        _WARMUP_STARTED = True

    if async_run:
        thread = threading.Thread(target=_warm, name="ocr-warmup", daemon=True)
        thread.start()
    else:
        _warm()


def run_ocr(
    image: Union[Image.Image, QImage],
    settings: OcrSettings,
    language_hint: LangHint = None,
) -> OcrResult:
    pil_image = _ensure_pil_image(image)
    available = get_available_languages()
    lang_string, missing, usable_langs = _normalize_languages(language_hint, settings, available)

    try:
        pytesseract.get_tesseract_version()
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Установите tesseract-ocr и перезапустите приложение."
        ) from exc

    def _perform(lang_value: Optional[str], config_value: str) -> str:
        return pytesseract.image_to_string(
            pil_image,
            lang=lang_value or None,
            config=config_value or "",
        )

    warnings: List[str] = []
    selected_config = ""
    data = None
    try:
        selected_config, data = _select_best_config(pil_image, lang_string, settings)
        text = _perform(lang_string, selected_config)
        language_tag = lang_string or "auto"
    except TesseractError as exc:
        if missing:
            try:
                selected_config, data = _select_best_config(pil_image, None, settings)
                text = _perform(None, selected_config)
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

    if data is None:
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang_string or None,
                config=selected_config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            data = None

    word_data: List[OcrWord] = []

    if data and all(key in data for key in ("text", "left", "top", "width", "height", "block_num", "par_num", "line_num")):
        for i, raw_text in enumerate(data["text"]):
            text_value = str(raw_text).strip()
            if not text_value:
                continue
            try:
                bbox = (
                    int(data["left"][i]),
                    int(data["top"][i]),
                    int(data["width"][i]),
                    int(data["height"][i]),
                )
                line_id = (
                    int(data.get("block_num", [0])[i]),
                    int(data.get("par_num", [0])[i]),
                    int(data.get("line_num", [0])[i]),
                )
            except Exception:
                continue
            word_data.append(OcrWord(text=text_value, bbox=bbox, line_id=line_id))

    return OcrResult(
        text=text.strip(),
        language_tag=language_tag,
        missing_languages=missing,
        fallback_used=language_tag == "auto" and bool(missing),
        warnings=warnings,
        languages_used=usable_langs,
        words=word_data,
    )
