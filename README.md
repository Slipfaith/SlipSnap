<!-- -*- coding: utf-8 -*- -->
# SlipSnap

SlipSnap is a desktop screenshot and short-video editor built with PySide6.  
Current version: **3.0**

---

## Русский

### Что нового в 3.0

- Централизована информация о версии/приложении в `main.py` (`APP_NAME`, `APP_VERSION`, `APP_DESCRIPTION`, `APP_AUTHOR`).
- Добавлен быстрый шаринг из редактора: кнопка **Поделиться ссылкой (24ч)**.
- Шаринг отправляет текущий экспорт (PNG или GIF) и копирует ссылку в буфер обмена.
- Улучшена работа с GIF:
  - вставка GIF из буфера/мем-библиотеки как анимированных элементов;
  - сохранение в GIF по умолчанию при анимированном контенте;
  - поддержка анимаций объектов и экспорт в анимированный GIF.
- Улучшены инструменты редактора:
  - Zoom Lens (лупа) как полноценный объект сцены;
  - анимации объектов (`Draw`, `Pulse`);
  - объединённая кнопка `Линия/Стрелка` с выбором через ПКМ.
- Обновлена библиотека мемов:
  - анимированные GIF-превью;
  - удаление и переименование мемов;
  - открытие папки мемов из UI;
  - сохранение размера окна.
- Видео-захват:
  - экспорт в MP4/GIF;
  - корректная работа UI записи и отмены;
  - улучшенная интеграция с GIF workflow.
- Улучшена обработка multi-monitor и DPI-сценариев при захвате области.

### Основные возможности

- Захват области и всего рабочего стола.
- Работа на 1–3+ мониторах с разным разрешением и DPI.
- Лончер + режим в трее (приложение не закрывается полностью при закрытии окна).
- Редактор с undo/redo, слоями, drag-and-drop и вставкой из буфера.
- OCR с выбором языков и вставкой результата на холст.
- Экспорт в PNG/JPG/GIF, видео в MP4/GIF.
- Мем-библиотека с поддержкой анимированных GIF.

### Шаринг (новое)

- Кнопка: **Поделиться ссылкой (24ч)** в верхнем тулбаре редактора.
- Сервис: `litterbox.catbox.moe` (временная ссылка, обычно до 24 часов).
- API-ключ не нужен.
- Ссылка автоматически копируется в буфер обмена.

Примечание: доступность ссылки зависит от внешнего сервиса и маршрута сети.

### Установка и запуск

Требования:

- Python 3.9+
- FFmpeg (для видео и конвертации MP4 -> GIF)

Установка:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Запуск:

```bash
python main.py
```

### Быстрый workflow

1. В лончере выбери `Снимок` или `Видео`.
2. Выдели область.
3. Отредактируй результат в Editor.
4. Сохрани, скопируй или нажми `Поделиться ссылкой (24ч)`.

### Горячие клавиши

Глобальные:

- `Ctrl+Alt+S` — запуск захвата (настраивается в конфиге)
- `Ctrl+Alt+V` — запуск записи видео (настраивается в конфиге)

Редактор:

- `Ctrl+N` — новый снимок
- `Ctrl+K` — история
- `Ctrl+C` — копировать
- `Ctrl+S` — сохранить
- `Ctrl+Z` / `Ctrl+Shift+Z` — undo/redo
- `Delete` — удалить выбранные элементы

### Конфиг

Файл: `~/.slipsnap_config.json`

Ключи (основные):

- `capture_hotkey`
- `video_hotkey`
- `video_duration_sec`
- `video_fps`
- `video_default_format`
- `video_last_save_directory`
- `meme_dialog_width`, `meme_dialog_height`
- `zoom_lens_size`, `zoom_lens_factor`

### Сборка с FFmpeg

1. Положи `ffmpeg.exe` в один из путей:
   - `ffmpeg.exe`
   - `ffmpeg/ffmpeg.exe`
   - `bin/ffmpeg.exe`
2. Собери `.exe`:
   - `pyinstaller SlipSnap.spec`
3. Собери инсталлятор:
   - `ISCC SlipSnap.iss`

---

## English

### What is new in 3.0

- App metadata/version is centralized in `main.py` (`APP_NAME`, `APP_VERSION`, `APP_DESCRIPTION`, `APP_AUTHOR`).
- New editor action: **Share link (24h)**.
- Sharing uploads current export (PNG or GIF) and copies URL to clipboard.
- Improved GIF workflow:
  - animated GIF paste from clipboard/meme library;
  - default GIF export for animated content;
  - object animations exported to animated GIF.
- Editor tool improvements:
  - Zoom Lens as a full scene object;
  - object animations (`Draw`, `Pulse`);
  - merged `Line/Arrow` tool button with right-click mode selection.
- Meme library updates:
  - animated GIF previews;
  - delete/rename memes;
  - open memes folder from UI;
  - persisted window size.
- Video capture updates:
  - MP4/GIF output;
  - better record UI/cancel handling;
  - tighter GIF workflow integration.
- Better region mapping in multi-monitor + mixed-DPI setups.

### Core features

- Region/full-screen capture.
- 1–3+ monitor support with mixed resolution and DPI.
- Launcher + tray mode.
- Editor with undo/redo, layers, drag-and-drop, clipboard paste.
- OCR flow with language selection.
- Export to PNG/JPG/GIF and video MP4/GIF.
- Meme library with animated GIF support.

### Sharing (new)

- Button: **Share link (24h)** in editor top toolbar.
- Provider: `litterbox.catbox.moe` (temporary URL, typically up to 24 hours).
- No API key required.
- URL is copied to clipboard automatically.

Note: link availability depends on the external hosting/CDN route.

### Install and run

Requirements:

- Python 3.9+
- FFmpeg (for video and MP4 -> GIF conversion)

Install:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Run:

```bash
python main.py
```

### Quick workflow

1. Choose `Screenshot` or `Video` in launcher.
2. Select capture region.
3. Edit in editor.
4. Save/copy/share with `Share link (24h)`.

### Build with bundled FFmpeg

1. Put `ffmpeg.exe` into one of:
   - `ffmpeg.exe`
   - `ffmpeg/ffmpeg.exe`
   - `bin/ffmpeg.exe`
2. Build app:
   - `pyinstaller SlipSnap.spec`
3. Build installer:
   - `ISCC SlipSnap.iss`
