# -*- coding: utf-8 -*-
"""Shared data models for Mistral and Gemini OCR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple


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
    warnings: list[str] = field(default_factory=list)
    languages_used: list[str] = field(default_factory=list)
    words: list[OcrWord] = field(default_factory=list)
    provider: str = "mistral"


@dataclass
class OcrSettings:
    preferred_languages: list[str] = field(default_factory=lambda: ["eng"])
    last_language: str = "auto"
    provider: str = "mistral"
    cloud_consents: list[str] = field(default_factory=list)

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
        provider = str(data.get("provider", "mistral")).strip().lower()
        if provider not in {"mistral", "gemini"}:
            provider = "mistral"
        raw_consents = data.get("cloud_consents", [])
        if not isinstance(raw_consents, list):
            raw_consents = []
        cloud_consents = list(
            dict.fromkeys(
                str(item).strip().lower()
                for item in raw_consents
                if str(item).strip().lower() in {"mistral", "gemini"}
            )
        )
        return cls(
            preferred_languages=preferred,
            last_language=last_language,
            provider=provider,
            cloud_consents=cloud_consents,
        )

    def to_dict(self) -> dict:
        return {
            "preferred_languages": list(self.preferred_languages),
            "last_language": self.last_language,
            "provider": self.provider,
            "cloud_consents": list(self.cloud_consents),
        }

    def remember_run(self, requested: str, languages_used: Sequence[str]) -> None:
        if requested:
            self.last_language = requested
        used = [str(lang).strip() for lang in languages_used if str(lang).strip()]
        if used:
            self.preferred_languages = list(dict.fromkeys(used))
