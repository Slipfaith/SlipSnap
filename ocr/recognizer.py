"""Tesseract OCR integration helpers."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pytesseract
from pytesseract import Output

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage


from logic import qimage_to_pil


class OcrError(RuntimeError):
    """Base error for OCR failures."""


class OcrUnavailableError(OcrError):
    """Raised when Tesseract OCR engine cannot be used."""


@dataclass
class OcrSpan:
    """Recognised text fragment and its bounding box."""

    text: str
    bbox: QRectF
    confidence: float


def _default_language() -> str:
    return os.environ.get("SLIPSNAP_OCR_LANG", "rus+eng")


class OcrEngine:
    """Lightweight wrapper around pytesseract for editor integration."""

    def __init__(
        self,
        language: Optional[str] = None,
        min_confidence: float = 65.0,
        tesseract_cmd: Optional[str] = None,
    ) -> None:
        self.language = language or _default_language()
        self.min_confidence = float(min_confidence)
        self._tesseract_cmd: Optional[str] = None
        self._configure_tesseract(tesseract_cmd)

    def _configure_tesseract(self, override: Optional[str]) -> None:
        """Resolve and apply a custom Tesseract executable path if provided."""

        candidate = override or os.environ.get("TESSERACT_CMD")
        if not candidate:
            self._tesseract_cmd = None
            return

        resolved = self._normalise_cmd(candidate)
        if not resolved.exists():
            raise OcrUnavailableError(
                f"Исполняемый файл Tesseract не найден по пути: {resolved}"
            )

        pytesseract.pytesseract.tesseract_cmd = str(resolved)
        self._tesseract_cmd = str(resolved)

    @staticmethod
    def _normalise_cmd(path_str: str) -> Path:
        path = Path(path_str).expanduser()
        if path.is_dir():
            executable = "tesseract.exe" if os.name == "nt" else "tesseract"
            path = path / executable
        return path

    def recognize(self, image: QImage) -> List[OcrSpan]:
        """Run OCR over the provided ``QImage`` and return grouped spans."""

        if image.isNull():
            return []

        pil_image = qimage_to_pil(image)
        if self._tesseract_cmd:
            cmd_path = Path(self._tesseract_cmd)
            if not cmd_path.exists():
                raise OcrUnavailableError(
                    f"Настроенный путь к Tesseract больше не существует: {cmd_path}"
                )
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=self.language,
                output_type=Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as exc:  # pragma: no cover - environment dependent
            raise OcrUnavailableError(
                "Tesseract OCR не найден. Установите пакет `tesseract-ocr` или укажите путь к"
                " исполняемому файлу в настройках."
            ) from exc
        except pytesseract.TesseractError as exc:  # pragma: no cover - passthrough error
            raise OcrError(str(exc)) from exc

        return self._group_lines(data)

    def _group_lines(self, data: Dict[str, Iterable]) -> List[OcrSpan]:
        texts: List[str] = data.get("text", [])  # type: ignore[assignment]
        if not texts:
            return []

        n = len(texts)
        left = data.get("left", [0] * n)
        top = data.get("top", [0] * n)
        width = data.get("width", [0] * n)
        height = data.get("height", [0] * n)
        conf = data.get("conf", [0] * n)
        page = data.get("page_num", [0] * n)
        block = data.get("block_num", [0] * n)
        par = data.get("par_num", [0] * n)
        line = data.get("line_num", [0] * n)

        spans: List[OcrSpan] = []

        current_key: Optional[Tuple[int, int, int, int]] = None
        current_text: List[str] = []
        current_conf: List[float] = []
        current_rect: Optional[QRectF] = None

        for idx in range(n):
            value = texts[idx].strip()
            if not value:
                continue

            try:
                conf_value = float(conf[idx])
            except (ValueError, TypeError):
                conf_value = 0.0

            if conf_value < self.min_confidence:
                continue

            key = (int(page[idx]), int(block[idx]), int(par[idx]), int(line[idx]))
            rect = QRectF(float(left[idx]), float(top[idx]), float(width[idx]), float(height[idx]))
            if rect.width() <= 1 or rect.height() <= 1:
                continue

            if current_key != key:
                if current_text and current_rect is not None:
                    spans.append(
                        OcrSpan(
                            text=" ".join(current_text),
                            bbox=current_rect,
                            confidence=sum(current_conf) / max(len(current_conf), 1),
                        )
                    )
                current_key = key
                current_text = [value]
                current_conf = [conf_value]
                current_rect = QRectF(rect)
            else:
                current_text.append(value)
                current_conf.append(conf_value)
                if current_rect is not None:
                    x1 = min(current_rect.left(), rect.left())
                    y1 = min(current_rect.top(), rect.top())
                    x2 = max(current_rect.right(), rect.right())
                    y2 = max(current_rect.bottom(), rect.bottom())
                    current_rect = QRectF(x1, y1, x2 - x1, y2 - y1)

        if current_text and current_rect is not None:
            spans.append(
                OcrSpan(
                    text=" ".join(current_text),
                    bbox=current_rect,
                    confidence=sum(current_conf) / max(len(current_conf), 1),
                )
            )

        return spans
