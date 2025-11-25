"""Склейка кадров скролл-захвата в одно изображение."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class ImageStitcher:
    """Строит длинное изображение из последовательности кадров."""

    def __init__(self) -> None:
        self.default_overlap = 200  # пикселей, если поиск не найден

    def stitch_frames(self, frames: Iterable[np.ndarray], output_path: str) -> str:
        """Склеивает кадры и сохраняет PNG.

        Parameters
        ----------
        frames: Iterable[np.ndarray]
            Список кадров в формате RGB.
        output_path: str
            Путь сохранения PNG.
        """
        frame_list: List[np.ndarray] = [f for f in frames if f is not None]
        if not frame_list:
            raise ValueError("Нет кадров для склейки")
        result = frame_list[0]
        for i in range(1, len(frame_list)):
            previous = result
            current = frame_list[i]
            offset = self._find_overlap_offset(previous, current)
            # Добавляем только уникальную часть
            unique_part = current[offset:]
            if unique_part.size == 0:
                continue
            result = np.vstack([previous, unique_part])
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        img = Image.fromarray(result.astype(np.uint8))
        img.save(output, optimize=True)
        return str(output)

    def _find_overlap_offset(self, img1: np.ndarray, img2: np.ndarray) -> int:
        """Находит смещение по Y между двумя кадрами."""
        if img1 is None or img2 is None:
            return self.default_overlap
        # Ограничиваем области поиска
        h1, w1, _ = img1.shape
        h2, w2, _ = img2.shape
        if w1 != w2:
            # Разная ширина – используем дефолт
            return self.default_overlap
        search1 = img1[int(h1 * 0.7) : h1]  # нижние 30%
        search2 = img2[: int(h2 * 0.3)]  # верхние 30%
        if search1.size == 0 or search2.size == 0:
            return self.default_overlap
        try:
            res = cv2.matchTemplate(search1, search2, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val < 0.5:
                return self.default_overlap
            # Позиция совпадения определяет пересечение
            overlap_y = max_loc[1]
            return max(int(h1 * 0.7) + overlap_y, self.default_overlap)
        except Exception:
            return self.default_overlap
