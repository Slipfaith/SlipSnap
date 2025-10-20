from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from local_ocr_client import LocalOCRClient, _parse_confidence


class _DummyOCR:
    class Output:
        DICT = 42

    def __init__(self, response):
        self._response = response
        self.calls = []

    def image_to_data(self, image, *, lang, output_type):  # type: ignore[override]
        self.calls.append((lang, output_type))
        return self._response


def test_recognize_handles_float_confidence_strings():
    data = {
        "text": ["Hello", "world", "", "ignored"],
        "conf": ["96.8", "54.2", "-1", "foo"],
        "left": [0, 10, 20, 30],
        "top": [0, 0, 0, 0],
        "width": [5, 5, 5, 5],
        "height": [5, 5, 5, 5],
    }
    ocr = _DummyOCR(data)
    client = LocalOCRClient(lang="eng", ocr_engine=ocr)
    image = Image.new("RGB", (10, 10), "white")

    text = client.recognize(image)

    assert text == "Hello world"
    assert ocr.calls == [("eng", ocr.Output.DICT)]


def test_parse_confidence_accepts_numeric_strings():
    assert _parse_confidence("96.8") == 96.8
    assert _parse_confidence("-1") == -1.0
    assert _parse_confidence(" 54 ") == 54.0
    assert _parse_confidence(None) is None
    assert _parse_confidence(12) == 12.0
    assert _parse_confidence("not-a-number") is None
