# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from ocr_models import OcrSettings


class OcrSettingsTests(unittest.TestCase):
    def test_cloud_settings_round_trip(self) -> None:
        settings = OcrSettings.from_config(
            {
                "ocr_settings": {
                    "preferred_languages": ["rus", "eng"],
                    "provider": "gemini",
                    "cloud_consents": ["gemini", "gemini", "invalid"],
                }
            }
        )

        self.assertEqual(settings.provider, "gemini")
        self.assertEqual(settings.cloud_consents, ["gemini"])
        self.assertEqual(settings.to_dict()["provider"], "gemini")

    def test_unknown_provider_falls_back_to_mistral(self) -> None:
        settings = OcrSettings.from_config(
            {"ocr_settings": {"provider": "unknown", "preferred_languages": ["eng"]}}
        )
        self.assertEqual(settings.provider, "mistral")


if __name__ == "__main__":
    unittest.main()
