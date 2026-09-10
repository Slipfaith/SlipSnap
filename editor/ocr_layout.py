# -*- coding: utf-8 -*-
"""Conservative pixel alignment for the coarse line boxes returned by cloud OCR."""

from PIL import Image
from PySide6.QtCore import QRectF


def _text_bands(image: Image.Image, rect: QRectF) -> list[QRectF]:
    """Find ink on a mostly flat UI background; leave ambiguous pictures alone.

    This only tightens existing OCR boxes, never recognizes or changes text.
    Work is done once per result, not while dragging or zooming the canvas.
    """
    bounds = rect.toAlignedRect().intersected(
        QRectF(0, 0, image.width, image.height).toRect()
    )
    if bounds.width() < 3 or bounds.height() < 3:
        return []
    crop = image.crop((bounds.left(), bounds.top(),
                       bounds.left() + bounds.width(), bounds.top() + bounds.height()))
    histogram = crop.histogram()
    background = max(range(256), key=histogram.__getitem__)
    flat_pixels = sum(histogram[max(0, background - 12):min(256, background + 13)])
    if flat_pixels < crop.width * crop.height * 0.55:
        return []
    mask = crop.point([255 if abs(value - background) >= 32 else 0
                       for value in range(256)])
    # A horizontal rule or a box edge is not a text row.
    rows = []
    for y in range(mask.height):
        count = mask.crop((0, y, mask.width, y + 1)).histogram()[255]
        if max(2, mask.width * 0.008) <= count < mask.width * 0.85:
            rows.append(y)
    if not rows:
        return []
    spans = []
    start = previous = rows[0]
    for y in rows[1:]:
        if y - previous > 3:
            spans.append((start, previous + 1))
            start = y
        previous = y
    spans.append((start, previous + 1))

    bands = []
    for top, bottom in spans:
        if bottom - top < 3:
            continue
        ink = mask.crop((0, top, mask.width, bottom)).getbbox()
        if ink is None:
            continue
        left, ink_top, right, ink_bottom = ink
        band = QRectF(bounds.left() + left, bounds.top() + top + ink_top,
                      right - left, ink_bottom - ink_top)
        bands.append(band.intersected(rect))
    return bands


def align_line_rects(
    image: Image.Image,
    rects: list[QRectF | None],
    groups: list[object],
) -> list[QRectF | None]:
    """Trim whitespace and align Mistral's evenly divided paragraph lines.

    Only accept a paragraph's pixel bands if their count matches its OCR lines.
    Individual boxes are tightened only when they contain one unambiguous band.
    """
    grayscale = image.convert("L")
    aligned = list(rects)
    grouped: dict[object, list[int]] = {}
    for index, group in enumerate(groups):
        if rects[index] is not None:
            grouped.setdefault(group, []).append(index)
    for indices in grouped.values():
        block = QRectF(rects[indices[0]])
        for index in indices[1:]:
            block = block.united(rects[index])
        bands = _text_bands(grayscale, block)
        if len(bands) == len(indices):
            for index, band in zip(indices, bands):
                aligned[index] = band
        else:
            for index in indices:
                bands = _text_bands(grayscale, rects[index])
                if len(bands) == 1:
                    aligned[index] = bands[0]
    return aligned
