# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import api_key_store


class _FakeCredentialError(Exception):
    pass


class ApiKeyStoreTests(unittest.TestCase):
    def test_environment_key_takes_priority(self) -> None:
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "from-env"}, clear=False):
            self.assertEqual(api_key_store.get_api_key("mistral"), "from-env")
            status = api_key_store.get_api_key_status("mistral")

        self.assertTrue(status.available)
        self.assertEqual(status.source, "MISTRAL_API_KEY")

    def test_windows_key_is_written_as_generic_credential(self) -> None:
        win32cred = SimpleNamespace(
            CRED_TYPE_GENERIC=1,
            CRED_PERSIST_LOCAL_MACHINE=2,
            CredWrite=Mock(),
        )
        pywintypes = SimpleNamespace(error=_FakeCredentialError)
        with (
            patch.object(api_key_store.sys, "platform", "win32"),
            patch.object(api_key_store, "_load_windows_modules", return_value=(win32cred, pywintypes)),
        ):
            api_key_store.set_api_key("gemini", "new-secret")

        credential = win32cred.CredWrite.call_args.args[0]
        self.assertEqual(credential["TargetName"], "SlipSnap/OCR/Gemini")
        self.assertEqual(credential["CredentialBlob"], "new-secret")

    def test_windows_unicode_blob_is_decoded_after_read(self) -> None:
        win32cred = SimpleNamespace(
            CRED_TYPE_GENERIC=1,
            CredRead=Mock(
                return_value={"CredentialBlob": "new-secret".encode("utf-16-le")}
            ),
        )
        pywintypes = SimpleNamespace(error=_FakeCredentialError)
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": ""},
                clear=False,
            ),
            patch.object(api_key_store.sys, "platform", "win32"),
            patch.object(api_key_store, "_load_windows_modules", return_value=(win32cred, pywintypes)),
        ):
            self.assertEqual(api_key_store.get_api_key("gemini"), "new-secret")

    def test_credential_type_error_is_wrapped_for_the_dialog(self) -> None:
        win32cred = SimpleNamespace(
            CRED_TYPE_GENERIC=1,
            CRED_PERSIST_LOCAL_MACHINE=2,
            CredWrite=Mock(side_effect=TypeError("unsupported blob")),
        )
        pywintypes = SimpleNamespace(error=_FakeCredentialError)
        with (
            patch.object(api_key_store.sys, "platform", "win32"),
            patch.object(api_key_store, "_load_windows_modules", return_value=(win32cred, pywintypes)),
        ):
            with self.assertRaises(api_key_store.ApiKeyStoreError):
                api_key_store.set_api_key("gemini", "new-secret")

    def test_settings_never_serialize_api_keys(self) -> None:
        from ocr_models import OcrSettings

        serialized = OcrSettings(provider="mistral").to_dict()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("mistral_api_key", serialized)
        self.assertNotIn("gemini_api_key", serialized)


if __name__ == "__main__":
    unittest.main()
