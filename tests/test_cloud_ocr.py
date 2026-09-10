# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import io
import json
import unittest
from unittest.mock import patch

import requests
from PIL import Image

from cloud_ocr import check_cloud_provider, run_cloud_ocr, run_ocr_with_provider
from ocr_models import OcrError, OcrResult, OcrSettings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._payload


class CloudOcrTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("RGB", (200, 100), "white")

    def test_mistral_ocr_parses_text_and_scales_blocks(self) -> None:
        response = _FakeResponse(
            200,
            {
                "pages": [
                    {
                        "markdown": "Hello world",
                        "dimensions": {"width": 100, "height": 50},
                        "blocks": [
                            {
                                "content": "Hello world",
                                "top_left_x": 10,
                                "top_left_y": 5,
                                "bottom_right_x": 90,
                                "bottom_right_y": 20,
                            }
                        ],
                    }
                ]
            },
        )
        with patch("cloud_ocr.requests.post", return_value=response) as post:
            result = run_cloud_ocr(self.image, "mistral", "eng", api_key="secret")

        self.assertEqual(result.text, "Hello world")
        self.assertEqual(result.provider, "mistral")
        self.assertEqual(result.words[0].bbox, (20, 10, 160, 30))
        request = post.call_args.kwargs
        self.assertEqual(request["headers"]["Authorization"], "Bearer secret")
        self.assertIn("data:image/png;base64,", request["json"]["document"]["image_url"])

    def test_gemini_ocr_parses_candidate_text(self) -> None:
        response = _FakeResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "Первая строка\nВторая строка"}]}}
                ]
            },
        )
        with patch("cloud_ocr.requests.post", return_value=response) as post:
            result = run_cloud_ocr(self.image, "gemini", "rus+eng", api_key="secret")

        self.assertEqual(result.text, "Первая строка\nВторая строка")
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.languages_used, ["rus", "eng"])
        request = post.call_args.kwargs
        self.assertEqual(request["headers"]["x-goog-api-key"], "secret")
        self.assertEqual(
            request["json"]["contents"][0]["parts"][1]["inline_data"]["mime_type"],
            "image/png",
        )
        self.assertEqual(
            request["json"]["generationConfig"]["responseMimeType"],
            "application/json",
        )

    def test_gemini_structured_lines_become_selectable_boxes(self) -> None:
        response = _FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "text": "First line\nSecond line",
                                            "lines": [
                                                {
                                                    "text": "First line",
                                                    "box": {
                                                        "left": 100,
                                                        "top": 200,
                                                        "right": 900,
                                                        "bottom": 400,
                                                    },
                                                },
                                                {
                                                    "text": "Second line",
                                                    "box": {
                                                        "left": 100,
                                                        "top": 500,
                                                        "right": 900,
                                                        "bottom": 700,
                                                    },
                                                },
                                            ],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

        with patch("cloud_ocr.requests.post", return_value=response):
            result = run_cloud_ocr(self.image, "gemini", "eng", api_key="secret")

        self.assertEqual(result.text, "First line\nSecond line")
        self.assertEqual([word.text for word in result.words], ["First line", "Second line"])
        self.assertEqual(result.words[0].bbox, (20, 20, 160, 20))
        self.assertEqual(result.words[1].bbox, (20, 50, 160, 20))

    def test_mistral_multiline_block_becomes_separate_selectable_lines(self) -> None:
        response = _FakeResponse(
            200,
            {
                "pages": [
                    {
                        "markdown": "First line\nSecond line",
                        "dimensions": {"width": 200, "height": 100},
                        "blocks": [
                            {
                                "content": "First line\nSecond line",
                                "top_left_x": 10,
                                "top_left_y": 20,
                                "bottom_right_x": 190,
                                "bottom_right_y": 60,
                            }
                        ],
                    }
                ]
            },
        )

        with patch("cloud_ocr.requests.post", return_value=response):
            result = run_cloud_ocr(self.image, "mistral", api_key="secret")

        self.assertEqual([word.text for word in result.words], ["First line", "Second line"])
        self.assertEqual(result.words[0].bbox, (10, 20, 180, 20))
        self.assertEqual(result.words[1].bbox, (10, 40, 180, 20))
        self.assertNotEqual(result.words[0].line_id, result.words[1].line_id)

    def test_transparent_canvas_is_flattened_onto_white(self) -> None:
        image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        image.putpixel((1, 1), (0, 0, 0, 255))
        response = _FakeResponse(200, {"pages": [{"markdown": "ok"}]})

        with patch("cloud_ocr.requests.post", return_value=response) as post:
            run_cloud_ocr(image, "mistral", api_key="secret")

        data_url = post.call_args.kwargs["json"]["document"]["image_url"]
        encoded = data_url.split(",", 1)[1]
        uploaded = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
        self.assertEqual(uploaded.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(uploaded.getpixel((1, 1)), (0, 0, 0))

    def test_transient_service_error_is_retried(self) -> None:
        busy = _FakeResponse(503, {"error": {"message": "busy"}})
        success = _FakeResponse(
            200,
            {"candidates": [{"content": {"parts": [{"text": "ready"}]}}]},
        )

        with (
            patch("cloud_ocr.requests.post", side_effect=[busy, success]) as post,
            patch("cloud_ocr.sleep") as retry_sleep,
        ):
            result = run_cloud_ocr(self.image, "gemini", api_key="secret")

        self.assertEqual(result.text, "ready")
        self.assertEqual(post.call_count, 2)
        retry_sleep.assert_called_once_with(0.5)

    def test_api_error_does_not_expose_key(self) -> None:
        response = _FakeResponse(401, {"error": {"message": "Invalid API key"}})
        with patch("cloud_ocr.requests.post", return_value=response):
            with self.assertRaises(OcrError) as raised:
                run_cloud_ocr(self.image, "gemini", api_key="do-not-leak")

        self.assertNotIn("do-not-leak", str(raised.exception))
        self.assertIn("отклонён", str(raised.exception))

    def test_selected_provider_is_dispatched_directly(self) -> None:
        settings = OcrSettings(provider="mistral")
        expected = OcrResult(text="cloud text", language_tag="eng", provider="mistral")
        with patch("cloud_ocr.run_cloud_ocr", return_value=expected) as cloud_request:
            result = run_ocr_with_provider(self.image, settings, "eng")

        self.assertIs(result, expected)
        cloud_request.assert_called_once_with(self.image, "mistral", "eng")

    def test_connection_check_uses_auth_header_without_uploading_image(self) -> None:
        response = _FakeResponse(200, {"data": []})
        with patch("cloud_ocr.requests.get", return_value=response) as get:
            check_cloud_provider("mistral", "secret")

        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer secret"})
        self.assertNotIn("json", get.call_args.kwargs)

    def test_timeout_has_readable_error(self) -> None:
        with patch("cloud_ocr.requests.post", side_effect=requests.Timeout):
            with self.assertRaisesRegex(OcrError, "не ответил вовремя"):
                run_cloud_ocr(self.image, "mistral", api_key="secret")


if __name__ == "__main__":
    unittest.main()
