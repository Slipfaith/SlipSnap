# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import QRectF

from editor.editor_window import EditorWindow, _OcrWorker
from editor.ocr_overlay import OcrCapture
from ocr_models import OcrResult, OcrSettings


class CloudOcrScannerFlowTests(unittest.TestCase):
    def _window_stub(self):
        events: list[str] = []
        capture = OcrCapture(
            image=Image.new("RGB", (40, 30), "white"),
            scene_rect=QRectF(0, 0, 40, 30),
            pixel_size=(40, 30),
        )
        window = SimpleNamespace(
            _ocr_worker=None,
            ocr_settings=OcrSettings(
                provider="mistral",
                preferred_languages=["eng"],
                cloud_consents=["mistral"],
            ),
            _open_ocr_cloud_settings=Mock(return_value=True),
            _reset_ocr_state=Mock(side_effect=lambda: events.append("reset")),
            _current_ocr_capture=Mock(
                side_effect=lambda: (events.append("capture"), capture)[1]
            ),
            _current_ocr_language_hint=Mock(return_value="eng"),
            _start_ocr_scan=Mock(side_effect=lambda _capture: events.append("scanner")),
            _on_ocr_worker_finished=Mock(),
        )
        return window, capture, events

    def test_saving_first_api_key_continues_into_scanner_and_request(self) -> None:
        window, capture, events = self._window_stub()
        worker = SimpleNamespace(
            finished=SimpleNamespace(connect=Mock()),
            start=Mock(side_effect=lambda: events.append("worker")),
        )
        with (
            patch("editor.editor_window.get_api_key", side_effect=["", "saved-key"]),
            patch("editor.editor_window._OcrWorker", return_value=worker),
        ):
            EditorWindow.rerun_ocr_with_language(window)

        window._open_ocr_cloud_settings.assert_called_once_with()
        window._start_ocr_scan.assert_called_once_with(capture)
        worker.start.assert_called_once_with()
        self.assertLess(events.index("scanner"), events.index("worker"))

    def test_canceling_key_dialog_does_not_start_scanner(self) -> None:
        window, _capture, _events = self._window_stub()
        window._open_ocr_cloud_settings.return_value = False
        with patch("editor.editor_window.get_api_key", return_value=""):
            EditorWindow.rerun_ocr_with_language(window)

        window._start_ocr_scan.assert_not_called()

    def test_existing_key_starts_immediately_without_consent_dialog(self) -> None:
        window, capture, events = self._window_stub()
        window.ocr_settings.cloud_consents = []
        worker = SimpleNamespace(
            finished=SimpleNamespace(connect=Mock()),
            start=Mock(side_effect=lambda: events.append("worker")),
        )
        with (
            patch("editor.editor_window.get_api_key", return_value="saved-key"),
            patch("editor.editor_window._OcrWorker", return_value=worker),
            patch("editor.editor_window.QMessageBox.question") as question,
        ):
            EditorWindow.rerun_ocr_with_language(window)

        question.assert_not_called()
        window._open_ocr_cloud_settings.assert_not_called()
        window._start_ocr_scan.assert_called_once_with(capture)
        worker.start.assert_called_once_with()
        self.assertLess(events.index("scanner"), events.index("worker"))

    def test_worker_keeps_scanner_visible_for_minimum_feedback_time(self) -> None:
        capture = OcrCapture(
            image=Image.new("RGB", (10, 10), "white"),
            scene_rect=QRectF(0, 0, 10, 10),
            pixel_size=(10, 10),
        )
        worker = _OcrWorker(capture, OcrSettings(provider="mistral"), "eng")
        result = OcrResult(text="ok", language_tag="eng", provider="mistral")
        emitted: list[tuple[object, object]] = []
        worker.finished.connect(lambda value, error: emitted.append((value, error)))

        with (
            patch("editor.editor_window.run_ocr_with_provider", return_value=result),
            patch("editor.editor_window.monotonic", side_effect=[10.0, 10.2]),
            patch("editor.editor_window.sleep") as sleep_mock,
        ):
            worker.run()

        sleep_mock.assert_called_once()
        self.assertAlmostEqual(sleep_mock.call_args.args[0], 0.7)
        self.assertEqual(emitted, [(result, None)])


if __name__ == "__main__":
    unittest.main()
