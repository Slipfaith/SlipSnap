"""Utilities for sending messages to Microsoft Teams."""

from __future__ import annotations

import base64
import json
from typing import Optional
from urllib import error, request


class TeamsSendError(Exception):
    """Raised when a message cannot be delivered to Microsoft Teams."""


def _build_message_card(
    user_name: str,
    user_email: str,
    message: str,
    image_bytes: Optional[bytes],
) -> dict:
    """Construct the payload for an incoming webhook message card."""

    identity = user_name.strip()
    if user_email.strip():
        identity = f"{identity} <{user_email.strip()}>"

    body_text_parts = []
    if message.strip():
        body_text_parts.append(message.strip())
    body_text_parts.append(f"Отправитель: {identity}")

    card: dict = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"Сообщение от {user_name}",
        "themeColor": "4B53BC",
        "title": f"SlipSnap — сообщение от {user_name}",
        "text": "\n\n".join(body_text_parts),
    }

    if image_bytes:
        image_data = base64.b64encode(image_bytes).decode("ascii")
        card.setdefault("sections", []).append(
            {
                "activityTitle": "Вложение",
                "activitySubtitle": "Скриншот из SlipSnap",
                "images": [
                    {
                        "image": f"data:image/png;base64,{image_data}",
                        "title": "Скриншот",
                    }
                ],
            }
        )

    return card


def send_message_to_teams(
    webhook_url: str,
    *,
    user_name: str,
    user_email: str = "",
    message: str = "",
    image_bytes: Optional[bytes] = None,
    timeout: int = 10,
) -> None:
    """Send a message to Microsoft Teams via an incoming webhook."""

    if not webhook_url:
        raise TeamsSendError("Не указан адрес вебхука Microsoft Teams")

    payload = _build_message_card(user_name, user_email, message, image_bytes)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", resp.getcode())
            if status >= 400:
                raise TeamsSendError(f"Сервер вернул ошибку HTTP {status}")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        detail = detail.strip() or str(exc.reason)
        raise TeamsSendError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise TeamsSendError(f"Не удалось подключиться к вебхуку: {exc.reason}") from exc
    except ValueError as exc:
        raise TeamsSendError(f"Некорректный адрес вебхука: {exc}") from exc
