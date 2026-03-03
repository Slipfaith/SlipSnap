# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from upload_service import UploadWorker


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = int(status_code)
        self.text = text


def _build_fake_requests(outcomes):
    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    class ConnectionError(RequestException):
        pass

    pending = list(outcomes)
    calls = []

    def post(url, data=None, files=None, timeout=None):
        calls.append(
            {
                "url": url,
                "data": data,
                "files": files,
                "timeout": timeout,
            }
        )
        if not pending:
            raise AssertionError("No fake outcome left for requests.post")
        outcome = pending.pop(0)
        if outcome == "timeout":
            raise Timeout("timed out")
        if outcome == "connection":
            raise ConnectionError("connection failed")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    fake_module = SimpleNamespace(
        post=post,
        exceptions=SimpleNamespace(
            RequestException=RequestException,
            Timeout=Timeout,
            ConnectionError=ConnectionError,
        ),
    )
    return fake_module, calls


class UploadWorkerTests(unittest.TestCase):
    def _temp_file(self, suffix: str = ".png") -> Path:
        fd, path = tempfile.mkstemp(prefix="slipsnap_upload_", suffix=suffix)
        os.close(fd)
        p = Path(path)
        p.write_bytes(b"fake-image-data")
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        return p

    def test_retries_after_timeout_and_succeeds(self) -> None:
        file_path = self._temp_file()
        fake_requests, calls = _build_fake_requests(
            [
                "timeout",
                _FakeResponse(200, "https://litterbox.catbox.moe/example.png"),
            ]
        )

        urls = []
        errors = []
        worker = UploadWorker(file_path)
        worker.finished.connect(urls.append)
        worker.failed.connect(errors.append)

        with (
            patch.dict(sys.modules, {"requests": fake_requests}),
            patch("upload_service.time.sleep", return_value=None),
        ):
            worker.run()

        self.assertEqual(errors, [])
        self.assertEqual(urls, ["https://litterbox.catbox.moe/example.png"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["timeout"], (10, 120))

    def test_all_timeouts_emit_readable_error(self) -> None:
        file_path = self._temp_file()
        fake_requests, calls = _build_fake_requests(
            ["timeout", "timeout", "timeout"]
        )

        urls = []
        errors = []
        worker = UploadWorker(file_path)
        worker.finished.connect(urls.append)
        worker.failed.connect(errors.append)

        with (
            patch.dict(sys.modules, {"requests": fake_requests}),
            patch("upload_service.time.sleep", return_value=None),
        ):
            worker.run()

        self.assertEqual(urls, [])
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(errors), 1)
        self.assertIn("долго не отвечает", errors[0])

    def test_retries_on_http_5xx_and_then_succeeds(self) -> None:
        file_path = self._temp_file()
        fake_requests, calls = _build_fake_requests(
            [
                _FakeResponse(503, "temporarily unavailable"),
                _FakeResponse(200, "https://litterbox.catbox.moe/ok.png"),
            ]
        )

        urls = []
        errors = []
        worker = UploadWorker(file_path)
        worker.finished.connect(urls.append)
        worker.failed.connect(errors.append)

        with (
            patch.dict(sys.modules, {"requests": fake_requests}),
            patch("upload_service.time.sleep", return_value=None),
        ):
            worker.run()

        self.assertEqual(errors, [])
        self.assertEqual(urls, ["https://litterbox.catbox.moe/ok.png"])
        self.assertEqual(len(calls), 2)

    def test_non_url_response_is_reported(self) -> None:
        file_path = self._temp_file()
        fake_requests, _ = _build_fake_requests(
            [
                _FakeResponse(200, "ERROR: invalid file"),
            ]
        )

        urls = []
        errors = []
        worker = UploadWorker(file_path)
        worker.finished.connect(urls.append)
        worker.failed.connect(errors.append)

        with patch.dict(sys.modules, {"requests": fake_requests}):
            worker.run()

        self.assertEqual(urls, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Неожиданный ответ сервера", errors[0])

    def test_missing_file_emits_error(self) -> None:
        missing = Path(tempfile.gettempdir()) / "slipsnap_missing_upload_file.tmp"
        missing.unlink(missing_ok=True)

        urls = []
        errors = []
        worker = UploadWorker(missing)
        worker.finished.connect(urls.append)
        worker.failed.connect(errors.append)
        worker.run()

        self.assertEqual(urls, [])
        self.assertEqual(errors, ["Не удалось найти файл для загрузки."])


if __name__ == "__main__":
    unittest.main()
