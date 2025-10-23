"""
Прямое копирование PNG в буфер через Win32 API
Qt добавляет слишком много лишних форматов - обходим его
"""
from __future__ import annotations

from io import BytesIO
import sys

from PIL import Image
from PySide6.QtGui import QImage

try:
    import win32clipboard as wc
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("WARNING: win32clipboard not available")


def copy_pil_image_to_clipboard(img: Image.Image) -> QImage:
    """Копирует PIL изображение в буфер с сохранением прозрачности

    Кладёт несколько форматов для совместимости:
    - PNG (для Telegram, современных программ)
    - CF_DIBV5 с альфа-каналом (для Teams, Word, Outlook)

    Returns:
        QImage для совместимости с существующим API
    """

    # Проверяем и конвертируем в RGBA
    if img.mode != "RGBA":
        print(f"Converting from {img.mode} to RGBA")
        img = img.convert("RGBA")

    # Диагностика альфа-канала
    extrema = img.getextrema()
    if len(extrema) == 4:
        alpha_min, alpha_max = extrema[3]
        print(f"Alpha channel range: {alpha_min} - {alpha_max}")
        if alpha_min == 255 and alpha_max == 255:
            print("WARNING: No transparency - alpha is always 255")

    # Сохраняем как PNG
    buffer = BytesIO()
    img.save(buffer, format="PNG", compress_level=6)
    png_data = buffer.getvalue()

    print(f"PNG size: {len(png_data)} bytes")

    # Создаём QImage для возврата
    qimg = QImage.fromData(png_data, "PNG")
    if qimg.format() != QImage.Format_ARGB32:
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

    # Копируем через Win32 API
    if HAS_WIN32 and sys.platform.startswith("win"):
        _copy_png_and_dibv5_win32(img, png_data)
    else:
        print("ERROR: Win32 clipboard not available")
        return qimg

    return qimg


def _copy_png_win32(png_data: bytes) -> None:
    """Копирует PNG в буфер через Win32 API"""

    try:
        wc.OpenClipboard()
        wc.EmptyClipboard()

        # Регистрируем формат PNG (если ещё не зарегистрирован)
        png_format = wc.RegisterClipboardFormat("PNG")

        # Кладём PNG данные
        wc.SetClipboardData(png_format, png_data)

        print(f"\n✓ Copied PNG to clipboard (format ID: {png_format})")
        print(f"  Size: {len(png_data)} bytes")

    except Exception as e:
        print(f"ERROR copying to clipboard: {e}")
    finally:
        try:
            wc.CloseClipboard()
        except:
            pass


def _create_dibv5_with_alpha(img: Image.Image) -> bytes:
    """Создаёт CF_DIBV5 с альфа-каналом для Teams/Word/Outlook

    DIBV5 = BITMAPV5HEADER (124 bytes) + pixel data в формате BGRA
    """
    import struct

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    width, height = img.size

    # Stride выравнивается по 4 байта
    stride = ((width * 32 + 31) // 32) * 4
    size_image = stride * height

    # BITMAPV5HEADER structure (124 bytes total)
    # Первая часть - стандартные поля до CSType включительно
    # Format: I=4, i=4, i=4, H=2, H=2, I=4, I=4, i=4, i=4, I=4, I=4, I=4, I=4, I=4, I=4, I=4
    # Total: 16 values
    header = struct.pack(
        '<IiiHHIIiiIIIIIII',  # 16 символов для 16 значений
        124,              # bV5Size (I)
        width,            # bV5Width (i)
        -height,          # bV5Height (i) - negative = top-down
        1,                # bV5Planes (H)
        32,               # bV5BitCount (H)
        3,                # bV5Compression (I) - BI_BITFIELDS
        size_image,       # bV5SizeImage (I)
        2835,             # bV5XPelsPerMeter (i) - ~72 DPI
        2835,             # bV5YPelsPerMeter (i)
        0,                # bV5ClrUsed (I)
        0,                # bV5ClrImportant (I)
        0x00FF0000,       # bV5RedMask (I) - R channel
        0x0000FF00,       # bV5GreenMask (I) - G channel
        0x000000FF,       # bV5BlueMask (I) - B channel
        0xFF000000,       # bV5AlphaMask (I) - A channel
        0x73524742,       # bV5CSType (I) - 'sRGB' in little-endian
    )

    # CIEXYZTRIPLE (36 bytes) - цветовое пространство (заполняем нулями)
    # 9 значений по 4 байта (3 точки * 3 координаты)
    endpoints = struct.pack('<9I', *([0] * 9))

    # Оставшиеся поля
    remaining = struct.pack(
        '<IIII',
        0,                # bV5GammaRed
        0,                # bV5GammaGreen
        0,                # bV5GammaBlue
        0,                # bV5Intent
    )

    # Последние поля
    final = struct.pack(
        '<III',
        0,                # bV5ProfileData
        0,                # bV5ProfileSize
        0,                # bV5Reserved
    )

    full_header = header + endpoints + remaining + final

    # Проверяем размер заголовка
    if len(full_header) != 124:
        raise ValueError(f"DIBV5 header size is {len(full_header)}, expected 124")

    # Конвертируем пиксели в BGRA
    pixel_data = img.tobytes("raw", "BGRA")

    return full_header + pixel_data


def _copy_png_and_dibv5_win32(img: Image.Image, png_data: bytes) -> None:
    """Копирует PNG + CF_DIBV5 для максимальной совместимости"""

    try:
        # Создаём DIBV5 с альфа-каналом
        dibv5_data = _create_dibv5_with_alpha(img)

        wc.OpenClipboard()
        wc.EmptyClipboard()

        # 1. PNG (приоритет для Telegram и современных программ)
        png_format = wc.RegisterClipboardFormat("PNG")
        wc.SetClipboardData(png_format, png_data)

        # 2. CF_DIBV5 (для Teams, Word, Outlook)
        wc.SetClipboardData(wc.CF_DIBV5, dibv5_data)

        print("\n✓ Copied to clipboard:")
        print(f"  PNG: {len(png_data)} bytes (for Telegram)")
        print(f"  CF_DIBV5: {len(dibv5_data)} bytes (for Teams/Word/Outlook)")

    except Exception as e:
        print(f"ERROR copying to clipboard: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            wc.CloseClipboard()
        except:
            pass


def copy_pil_image_to_clipboard_with_fallback(img: Image.Image) -> QImage:
    """Копирует PNG + CF_DIB для совместимости со старыми программами

    Некоторые старые программы не понимают PNG, поэтому добавляем CF_DIB.
    Но CF_DIB кладём БЕЗ альфа-канала, чтобы не сломать прозрачность в современных программах.
    """

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # PNG с прозрачностью
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    # Создаём QImage
    qimg = QImage.fromData(png_data, "PNG")
    if qimg.format() != QImage.Format_ARGB32:
        qimg = qimg.convertToFormat(QImage.Format_ARGB32)

    if not (HAS_WIN32 and sys.platform.startswith("win")):
        return qimg

    # CF_DIB для старых программ (RGB без альфы, чтобы не конфликтовать)
    img_rgb = img.convert("RGB")
    dib_buffer = BytesIO()
    img_rgb.save(dib_buffer, format="BMP")
    dib_data = dib_buffer.getvalue()[14:]  # Убираем BMP file header

    try:
        wc.OpenClipboard()
        wc.EmptyClipboard()

        # Сначала PNG (приоритет!)
        png_format = wc.RegisterClipboardFormat("PNG")
        wc.SetClipboardData(png_format, png_data)

        # Потом CF_DIB для совместимости
        wc.SetClipboardData(wc.CF_DIB, dib_data)

        print("\n✓ Copied to clipboard:")
        print(f"  PNG: {len(png_data)} bytes (with transparency)")
        print(f"  CF_DIB: {len(dib_data)} bytes (fallback for old apps)")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        try:
            wc.CloseClipboard()
        except:
            pass

    return qimg


# Для тестирования
def test_copy():
    """Тест копирования прозрачного изображения"""
    from PIL import ImageDraw

    # Создаём тестовое изображение
    img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))  # Прозрачный фон
    draw = ImageDraw.Draw(img)
    draw.ellipse([50, 50, 150, 150], fill=(0, 255, 0, 255))  # Зелёный круг

    print("=== Тестовое изображение ===")
    print(f"Size: {img.size}, Mode: {img.mode}")

    pixels = img.load()
    print(f"Corner (0,0): {pixels[0, 0]} - should be transparent")
    print(f"Center (100,100): {pixels[100, 100]} - should be green")

    # Копируем (теперь PNG + CF_DIBV5)
    copy_pil_image_to_clipboard(img)

    # Сохраняем для проверки
    img.save("test_transparent.png")
    print("\n✓ Saved test_transparent.png - check it in browser")
    print("\nFormats in clipboard:")
    print("  - PNG → for Telegram, modern apps")
    print("  - CF_DIBV5 → for Teams, Word, Outlook")


if __name__ == "__main__":
    test_copy()
    print("\nNow try pasting in:")
    print("  1. Teams (should use CF_DIBV5)")
    print("  2. Telegram (should use PNG)")
    print("  3. Word (should use CF_DIBV5)")
    print("  4. Outlook (should use CF_DIBV5)")
