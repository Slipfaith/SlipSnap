<!-- -*- coding: utf-8 -*- -->
# SlipSnap

> **RU:** Десктопный инструмент для захвата экрана и записи коротких видео с редактором аннотаций.
> **EN:** A desktop screenshot and short-video capture tool with a built-in annotation editor.

**Версия / Version:** 3.0

---

## Возможности / Features

| RU | EN |
|----|----|
| Захват области и всего рабочего стола | Region and full-screen capture |
| Поддержка 1–3+ мониторов с разным DPI | 1–3+ monitor support with mixed DPI |
| Лончер + режим в трее | Launcher + system tray mode |
| Редактор с undo/redo, слоями, drag-and-drop | Editor with undo/redo, layers, drag-and-drop |
| OCR с выбором языка, вставка текста на холст | OCR with language selection, paste to canvas |
| Zoom Lens — лупа как объект сцены | Zoom Lens as a full scene object |
| Анимации объектов (Draw, Pulse) | Object animations (Draw, Pulse) |
| Мем-библиотека с анимированными GIF | Meme library with animated GIF support |
| Запись видео, экспорт в MP4 / GIF | Video capture, export to MP4 / GIF |
| Экспорт в PNG / JPG / GIF | Export to PNG / JPG / GIF |
| Быстрый шаринг — ссылка на 24ч | Quick share — temporary link for 24h |

---

## Быстрый старт / Quick Start

| RU | EN |
|----|----|
| 1. Запусти лончер | 1. Open the launcher |
| 2. Выбери `Снимок` или `Видео` | 2. Choose `Screenshot` or `Video` |
| 3. Выдели область экрана | 3. Select capture region |
| 4. Отредактируй в Editor | 4. Edit in the editor |
| 5. Сохрани, скопируй или нажми `Поделиться ссылкой (24ч)` | 5. Save, copy, or click `Share link (24h)` |

---

## Горячие клавиши / Hotkeys

### Глобальные / Global

| Клавиши / Keys | RU | EN |
|---|---|---|
| `Ctrl+Alt+S` | Запуск захвата экрана | Launch screenshot capture |
| `Ctrl+Alt+V` | Запуск записи видео | Launch video recording |

> Горячие клавиши настраиваются в конфиге / Hotkeys are configurable in config.

### Редактор / Editor

| Клавиши / Keys | RU | EN |
|---|---|---|
| `Ctrl+N` | Новый снимок | New screenshot |
| `Ctrl+K` | История | History |
| `Ctrl+C` | Копировать | Copy |
| `Ctrl+S` | Сохранить | Save |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / Redo | Undo / Redo |
| `Delete` | Удалить выбранные элементы | Delete selected items |

---

## Шаринг / Quick Share

- **RU:** Кнопка **«Поделиться ссылкой (24ч)»** в тулбаре редактора. Загружает текущий PNG/GIF на `litterbox.catbox.moe` и копирует ссылку в буфер. API-ключ не нужен.
- **EN:** Click **«Share link (24h)»** in the editor toolbar. Uploads current PNG/GIF to `litterbox.catbox.moe` and copies the URL to clipboard. No API key required.

> RU: Доступность ссылки зависит от внешнего сервиса.
> EN: Link availability depends on the external hosting provider.

---

## Конфиг / Config

Файл / File: `~/.slipsnap_config.json`

| Ключ / Key | Описание RU | Description EN |
|---|---|---|
| `capture_hotkey` | Горячая клавиша захвата | Screenshot hotkey |
| `video_hotkey` | Горячая клавиша видео | Video hotkey |
| `video_duration_sec` | Макс. длина видео (сек) | Max video duration (sec) |
| `video_fps` | FPS записи | Recording FPS |
| `video_default_format` | Формат по умолчанию (mp4/gif) | Default format (mp4/gif) |
| `zoom_lens_size` | Размер лупы | Zoom lens size |
| `zoom_lens_factor` | Коэффициент увеличения | Zoom lens factor |

---

## Установка / Installation

### Исполняемый файл / Executable

Скачайте установщик из [Releases](../../releases) и запустите — Python не нужен.
Download the installer from [Releases](../../releases) — no Python required.

### Из исходников / From Source

```bash
git clone https://github.com/Slipfaith/SlipSnap.git
cd SlipSnap
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

**Требования / Requirements:** Python 3.9+, [FFmpeg](https://ffmpeg.org/) *(для видео / for video)*

---

## Сборка / Build

```bash
# Положи ffmpeg.exe в корень проекта / Put ffmpeg.exe in project root
pyinstaller SlipSnap.spec        # → dist\SlipSnap.exe
ISCC SlipSnap.iss                # → installer .exe
```

---

## Что нового в 3.0 / What's New in 3.0

- **RU:** Быстрый шаринг, анимации объектов (Draw/Pulse), Zoom Lens как объект сцены, вставка анимированных GIF из буфера и мем-библиотеки, улучшена запись видео и поддержка multi-monitor + DPI.
- **EN:** Quick share action, object animations (Draw/Pulse), Zoom Lens as scene object, animated GIF paste from clipboard and meme library, improved video capture and multi-monitor + DPI handling.

Подробнее / Full details: [CHANGELOG.md](CHANGELOG.md)

---

## Лицензия / License

MIT
