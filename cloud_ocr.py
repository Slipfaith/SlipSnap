# -*- coding: utf-8 -*-
"""Mistral and Gemini OCR clients used by SlipSnap."""

from __future__ import annotations

import base64
import io
import json
from time import sleep
from typing import Any, Sequence

import requests
from PIL import Image

from api_key_store import get_api_key
from ocr_models import OcrError, OcrResult, OcrSettings, OcrWord


PROVIDER_NAMES = {
    "mistral": "Mistral OCR",
    "gemini": "Google Gemini",
}
MISTRAL_MODEL = "mistral-ocr-latest"
GEMINI_MODEL = "gemini-3.6-flash"
_MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
_MISTRAL_MODELS_URL = "https://api.mistral.ai/v1/models"
_GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_CONNECT_TIMEOUT_SECONDS = 8
_READ_TIMEOUT_SECONDS = 60
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRY_DELAYS_SECONDS = (0.5, 1.0)


def _normalized_languages(language_hint: str | Sequence[str] | None) -> list[str]:
    if isinstance(language_hint, str):
        values = language_hint.replace(",", "+").split("+")
    elif language_hint:
        values = list(language_hint)
    else:
        values = []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _encoded_png(image: Image.Image) -> str:
    if "A" in image.getbands():
        rgba = image.convert("RGBA")
        normalized = Image.new("RGB", rgba.size, "white")
        normalized.paste(rgba, mask=rgba.getchannel("A"))
    else:
        normalized = image.convert("RGB") if image.mode not in {"RGB", "L"} else image
    buffer = io.BytesIO()
    normalized.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _safe_api_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
    else:
        message = payload.get("message")
    if not isinstance(message, str):
        return ""
    return " ".join(message.split())[:240]


def _request_error(provider_name: str, response: requests.Response) -> OcrError:
    detail = _safe_api_message(response)
    suffix = f" {detail}" if detail else ""
    if response.status_code in {401, 403}:
        return OcrError(f"{provider_name}: API-ключ отклонён.{suffix}")
    if response.status_code == 429:
        return OcrError(f"{provider_name}: исчерпана квота или слишком много запросов.{suffix}")
    return OcrError(f"{provider_name}: сервис вернул HTTP {response.status_code}.{suffix}")


def _post_json(
    url: str,
    *,
    provider_name: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
            )
        except requests.Timeout as exc:
            raise OcrError(
                "Облачный OCR не ответил вовремя. Проверьте интернет и повторите."
            ) from exc
        except requests.RequestException as exc:
            raise OcrError("Не удалось подключиться к облачному OCR. Проверьте интернет.") from exc
        if response.ok:
            break
        if (
            response.status_code not in _RETRYABLE_STATUS_CODES
            or attempt >= len(_RETRY_DELAYS_SECONDS)
        ):
            raise _request_error(provider_name, response)
        sleep(_RETRY_DELAYS_SECONDS[attempt])
    try:
        data = response.json()
    except ValueError as exc:
        raise OcrError("Облачный OCR вернул некорректный ответ.") from exc
    if not isinstance(data, dict):
        raise OcrError("Облачный OCR вернул неожиданный формат ответа.")
    return data


def _mistral_words(payload: dict[str, Any], image_size: tuple[int, int]) -> list[OcrWord]:
    words: list[OcrWord] = []
    image_width, image_height = image_size
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return words
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        dimensions = page.get("dimensions")
        page_width = image_width
        page_height = image_height
        if isinstance(dimensions, dict):
            page_width = int(dimensions.get("width") or image_width)
            page_height = int(dimensions.get("height") or image_height)
        scale_x = image_width / max(1, page_width)
        scale_y = image_height / max(1, page_height)
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            content_lines = [
                line.strip()
                for line in str(block.get("content") or "").splitlines()
                if line.strip()
            ]
            if not content_lines:
                continue
            try:
                left = round(float(block["top_left_x"]) * scale_x)
                top = round(float(block["top_left_y"]) * scale_y)
                right = round(float(block["bottom_right_x"]) * scale_x)
                bottom = round(float(block["bottom_right_y"]) * scale_y)
            except (KeyError, TypeError, ValueError):
                continue
            if right <= left or bottom <= top:
                continue
            block_height = bottom - top
            for line_index, content in enumerate(content_lines):
                line_top = round(top + block_height * line_index / len(content_lines))
                line_bottom = round(
                    top + block_height * (line_index + 1) / len(content_lines)
                )
                words.append(
                    OcrWord(
                        text=content,
                        bbox=(
                            left,
                            line_top,
                            right - left,
                            max(1, line_bottom - line_top),
                        ),
                        line_id=(page_index, block_index, line_index),
                    )
                )
    return words


def _run_mistral(
    image: Image.Image, api_key: str, languages: list[str]
) -> OcrResult:
    payload = _post_json(
        _MISTRAL_OCR_URL,
        provider_name=PROVIDER_NAMES["mistral"],
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload={
            "model": MISTRAL_MODEL,
            "document": {
                "type": "image_url",
                "image_url": f"data:image/png;base64,{_encoded_png(image)}",
            },
            "include_image_base64": False,
            "include_blocks": True,
        },
    )
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise OcrError("Mistral OCR вернул ответ без распознанных страниц.")
    page_text = [
        str(page.get("markdown") or "").strip()
        for page in pages
        if isinstance(page, dict) and str(page.get("markdown") or "").strip()
    ]
    return OcrResult(
        text="\n\n".join(page_text),
        language_tag="+".join(languages) or "auto",
        languages_used=languages,
        words=_mistral_words(payload, image.size),
        provider="mistral",
    )


def _gemini_prompt(languages: list[str]) -> str:
    language_note = ", ".join(languages) if languages else "определи автоматически"
    return (
        "Распознай весь видимый текст на изображении максимально точно. "
        "Сохрани порядок чтения, переносы строк, регистр, числа и знаки препинания. "
        "Для каждой визуальной строки верни её прямоугольник с координатами left, top, right, "
        "bottom в целых числах от 0 до 1000 относительно изображения. "
        "Не объясняй результат и не добавляй Markdown. "
        f"Ожидаемые языки: {language_note}."
    )


def _gemini_result(
    response_text: str,
    image_size: tuple[int, int],
    languages: list[str],
) -> OcrResult:
    try:
        structured = json.loads(response_text)
    except (TypeError, ValueError):
        structured = None

    if not isinstance(structured, dict):
        return OcrResult(
            text=response_text,
            language_tag="+".join(languages) or "auto",
            languages_used=languages,
            provider="gemini",
        )

    lines = structured.get("lines")
    words: list[OcrWord] = []
    fallback_lines: list[str] = []
    image_width, image_height = image_size
    if isinstance(lines, list):
        for line_index, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            box = line.get("box")
            if not text:
                continue
            fallback_lines.append(text)
            if not isinstance(box, dict):
                continue
            try:
                left = max(0.0, min(1000.0, float(box["left"])))
                top = max(0.0, min(1000.0, float(box["top"])))
                right = max(0.0, min(1000.0, float(box["right"])))
                bottom = max(0.0, min(1000.0, float(box["bottom"])))
            except (KeyError, TypeError, ValueError):
                continue
            pixel_left = round(left * image_width / 1000)
            pixel_top = round(top * image_height / 1000)
            pixel_right = round(right * image_width / 1000)
            pixel_bottom = round(bottom * image_height / 1000)
            if pixel_right <= pixel_left or pixel_bottom <= pixel_top:
                continue
            words.append(
                OcrWord(
                    text=text,
                    bbox=(
                        pixel_left,
                        pixel_top,
                        pixel_right - pixel_left,
                        pixel_bottom - pixel_top,
                    ),
                    line_id=(0, line_index, 0),
                )
            )

    full_text = str(structured.get("text") or "").strip()
    if not full_text:
        full_text = "\n".join(fallback_lines)
    return OcrResult(
        text=full_text,
        language_tag="+".join(languages) or "auto",
        languages_used=languages,
        words=words,
        provider="gemini",
    )


def _run_gemini(
    image: Image.Image, api_key: str, languages: list[str]
) -> OcrResult:
    payload = _post_json(
        f"{_GEMINI_API_ROOT}/models/{GEMINI_MODEL}:generateContent",
        provider_name=PROVIDER_NAMES["gemini"],
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        payload={
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": _gemini_prompt(languages)},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": _encoded_png(image),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING"},
                        "lines": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "text": {"type": "STRING"},
                                    "box": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "left": {"type": "INTEGER"},
                                            "top": {"type": "INTEGER"},
                                            "right": {"type": "INTEGER"},
                                            "bottom": {"type": "INTEGER"},
                                        },
                                        "required": ["left", "top", "right", "bottom"],
                                    },
                                },
                                "required": ["text", "box"],
                            },
                        },
                    },
                    "required": ["text", "lines"],
                },
            },
        },
    )
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise OcrError("Gemini не вернул распознанный текст. Возможно, запрос был заблокирован.")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        finish_reason = (
            str(candidates[0].get("finishReason") or "").strip()
            if isinstance(candidates[0], dict)
            else ""
        )
        suffix = f" Причина: {finish_reason}." if finish_reason else ""
        raise OcrError(f"Gemini вернул неожиданный формат ответа.{suffix}")
    response_text = "\n".join(
        str(part.get("text") or "").strip()
        for part in parts
        if isinstance(part, dict) and str(part.get("text") or "").strip()
    )
    return _gemini_result(response_text, image.size, languages)


def run_cloud_ocr(
    image: Image.Image,
    provider: str,
    language_hint: str | Sequence[str] | None = None,
    *,
    api_key: str | None = None,
) -> OcrResult:
    normalized = str(provider).strip().lower()
    if normalized not in {"mistral", "gemini"}:
        raise ValueError(f"Неизвестный облачный OCR-провайдер: {provider}")
    key = str(api_key or get_api_key(normalized)).strip()
    if not key:
        raise OcrError(
            f"Для {PROVIDER_NAMES[normalized]} не задан API-ключ. Откройте настройки OCR API."
        )
    languages = _normalized_languages(language_hint)
    if normalized == "mistral":
        return _run_mistral(image, key, languages)
    return _run_gemini(image, key, languages)


def run_ocr_with_provider(
    image: Image.Image,
    settings: OcrSettings,
    language_hint: str | Sequence[str] | None = None,
) -> OcrResult:
    return run_cloud_ocr(image, settings.provider, language_hint)


def check_cloud_provider(provider: str, api_key: str | None = None) -> None:
    normalized = str(provider).strip().lower()
    if normalized not in {"mistral", "gemini"}:
        raise ValueError(f"Неизвестный облачный OCR-провайдер: {provider}")
    key = str(api_key or get_api_key(normalized)).strip()
    if not key:
        raise OcrError("Сначала введите API-ключ.")
    if normalized == "mistral":
        url = _MISTRAL_MODELS_URL
        headers = {"Authorization": f"Bearer {key}"}
    else:
        url = f"{_GEMINI_API_ROOT}/models?pageSize=1"
        headers = {"x-goog-api-key": key}
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=(_CONNECT_TIMEOUT_SECONDS, 20),
        )
    except requests.Timeout as exc:
        raise OcrError("Сервис не ответил вовремя.") from exc
    except requests.RequestException as exc:
        raise OcrError("Не удалось подключиться к сервису. Проверьте интернет.") from exc
    if not response.ok:
        raise _request_error(PROVIDER_NAMES[normalized], response)
