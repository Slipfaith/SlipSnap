# -*- coding: utf-8 -*-
"""Secure storage for cloud OCR API keys."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


class ApiKeyStoreError(RuntimeError):
    """Raised when a key cannot be read from or written to secure storage."""


@dataclass(frozen=True)
class ApiKeyStatus:
    available: bool
    source: str = ""


_PROVIDER_TARGETS = {
    "mistral": "SlipSnap/OCR/Mistral",
    "gemini": "SlipSnap/OCR/Gemini",
}
_PROVIDER_ENV_VARS = {
    "mistral": ("MISTRAL_API_KEY", "MISTRALAPI"),
    "gemini": ("GEMINI_API_KEY",),
}
_CREDENTIAL_NOT_FOUND = 1168


def _normalize_provider(provider: str) -> str:
    normalized = str(provider).strip().lower()
    if normalized not in _PROVIDER_TARGETS:
        raise ValueError(f"Неизвестный OCR-провайдер: {provider}")
    return normalized


def _environment_key(provider: str) -> tuple[str, str]:
    for variable in _PROVIDER_ENV_VARS[provider]:
        value = os.environ.get(variable, "").strip()
        if value:
            return value, variable
    return "", ""


def _load_windows_modules():
    try:
        import pywintypes
        import win32cred
    except ImportError as exc:
        raise ApiKeyStoreError(
            "Защищённое хранилище Windows недоступно. Переустановите SlipSnap."
        ) from exc
    return win32cred, pywintypes


def _is_not_found_error(exc: BaseException) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror == _CREDENTIAL_NOT_FOUND:
        return True
    return bool(exc.args and exc.args[0] == _CREDENTIAL_NOT_FOUND)


def _decode_blob(blob: object) -> str:
    if isinstance(blob, bytes):
        # CredWrite accepts str, while CredRead exposes that value as UTF-16LE bytes.
        # Keep UTF-8 support for credentials created by older/custom tools.
        if blob.startswith((b"\xff\xfe", b"\xfe\xff")):
            return blob.decode("utf-16").rstrip("\x00").strip()
        if b"\x00" in blob:
            return blob.decode("utf-16-le").rstrip("\x00").strip()
        return blob.decode("utf-8").strip()
    return str(blob or "").strip()


def get_api_key(provider: str) -> str:
    """Return a key from the environment or Windows Credential Manager."""

    normalized = _normalize_provider(provider)
    environment_key, _ = _environment_key(normalized)
    if environment_key:
        return environment_key
    if sys.platform != "win32":
        return ""

    win32cred, pywintypes = _load_windows_modules()
    try:
        credential = win32cred.CredRead(
            _PROVIDER_TARGETS[normalized], win32cred.CRED_TYPE_GENERIC, 0
        )
    except pywintypes.error as exc:
        if _is_not_found_error(exc):
            return ""
        raise ApiKeyStoreError(
            "Не удалось прочитать API-ключ из диспетчера учётных данных Windows."
        ) from exc
    return _decode_blob(credential.get("CredentialBlob"))


def get_api_key_status(provider: str) -> ApiKeyStatus:
    normalized = _normalize_provider(provider)
    environment_key, variable = _environment_key(normalized)
    if environment_key:
        return ApiKeyStatus(True, variable)
    key = get_api_key(normalized)
    return ApiKeyStatus(bool(key), "Windows Credential Manager" if key else "")


def set_api_key(provider: str, api_key: str) -> None:
    """Save a key without ever placing it in SlipSnap's JSON configuration."""

    normalized = _normalize_provider(provider)
    value = str(api_key).strip()
    if not value:
        raise ValueError("API-ключ не может быть пустым.")
    if sys.platform != "win32":
        raise ApiKeyStoreError(
            "Сохранение ключей поддерживается только через диспетчер учётных данных Windows."
        )

    win32cred, pywintypes = _load_windows_modules()
    credential = {
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": _PROVIDER_TARGETS[normalized],
        "UserName": "SlipSnap",
        # pywin32's Unicode CredWrite wrapper expects a Python str here.
        # Passing bytes raises "Objects of type 'bytes' can not be converted to Unicode".
        "CredentialBlob": value,
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        "Comment": "SlipSnap cloud OCR API key",
    }
    try:
        win32cred.CredWrite(credential, 0)
    except (pywintypes.error, TypeError, ValueError) as exc:
        raise ApiKeyStoreError(
            "Не удалось сохранить API-ключ в диспетчере учётных данных Windows."
        ) from exc


def delete_api_key(provider: str) -> None:
    normalized = _normalize_provider(provider)
    if sys.platform != "win32":
        return
    win32cred, pywintypes = _load_windows_modules()
    try:
        win32cred.CredDelete(_PROVIDER_TARGETS[normalized], win32cred.CRED_TYPE_GENERIC, 0)
    except pywintypes.error as exc:
        if _is_not_found_error(exc):
            return
        raise ApiKeyStoreError(
            "Не удалось удалить API-ключ из диспетчера учётных данных Windows."
        ) from exc
