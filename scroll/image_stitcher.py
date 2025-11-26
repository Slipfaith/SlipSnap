"""Сборка длинного изображения из серии кадров."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import cv2
import numpy as np
from PIL import Image


class ImageStitcher:
    """Склеивает кадры, убирая дублирующийся overlap."""

    def __init__(self, frames: Iterable[np.ndarray]):
        self.frames = list(frames)

    @staticmethod
    def _to_pil(frame: np.ndarray) -> Image.Image:
        if frame is None:
            raise ValueError("Пустой кадр")
        if frame.ndim == 3 and frame.shape[2] == 4:
            # RGBA -> RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
        elif frame.ndim == 3 and frame.shape[2] == 3:
            # Считаем, что кадр уже в RGB и просто создаём Image
            frame = frame.copy()
        else:
            raise ValueError("Неподдерживаемый формат кадра")
        return Image.fromarray(frame)

    @staticmethod
    def _find_overlap(frame_a: np.ndarray, frame_b: np.ndarray) -> Tuple[int, float]:
        """Возвращает смещение по Y, используя template matching."""
        ha, wa = frame_a.shape[:2]
        hb, wb = frame_b.shape[:2]
        if ha == 0 or hb == 0:
            return 0, 0.0
        bottom_a = frame_a[int(ha * 0.7):, :wa]
        top_b = frame_b[: int(hb * 0.3), :wb]
        # Подгоняем ширину если кадры отличаются
        width = min(bottom_a.shape[1], top_b.shape[1])
        bottom_a = bottom_a[:, :width]
        top_b = top_b[:, :width]
        if bottom_a.shape[0] == 0 or top_b.shape[0] == 0:
            return 0, 0.0

        gray_a = cv2.cvtColor(bottom_a, cv2.COLOR_RGBA2GRAY if bottom_a.shape[2] == 4 else cv2.COLOR_RGB2GRAY)
        gray_b = cv2.cvtColor(top_b, cv2.COLOR_RGBA2GRAY if top_b.shape[2] == 4 else cv2.COLOR_RGB2GRAY)
        if gray_a.shape[0] > gray_b.shape[0]:
            gray_a = gray_a[-gray_b.shape[0]:, :]
        res = cv2.matchTemplate(gray_b, gray_a, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        overlap_height = gray_a.shape[0]
        y_offset = max_loc[1]
        return y_offset + overlap_height, max_val

    def stitch(self, output_path: Path) -> Path:
        if not self.frames:
            raise ValueError("Нет кадров для склейки")

        base_image = self._to_pil(self.frames[0])
        for idx in range(1, len(self.frames)):
            frame = self.frames[idx]
            try:
                offset, confidence = self._find_overlap(self.frames[idx - 1], frame)
            except Exception:
                offset, confidence = (int(frame.shape[0] * 0.2), 0.0)
            # Если не нашли достоверное совпадение — используем фиксированный отступ
            if confidence < 0.6:
                offset = min(frame.shape[0], max(50, int(frame.shape[0] * 0.3)))

            append_region = frame[offset:]
            if append_region.size == 0:
                continue
            next_part = self._to_pil(append_region)
            new_width = max(base_image.width, next_part.width)
            new_height = base_image.height + next_part.height
            combined = Image.new("RGB", (new_width, new_height), color=(255, 255, 255))
            combined.paste(base_image, (0, 0))
            combined.paste(next_part, (0, base_image.height))
            base_image = combined

        output_path.parent.mkdir(parents=True, exist_ok=True)
        base_image.save(output_path, format="PNG", optimize=True)
        return output_path
