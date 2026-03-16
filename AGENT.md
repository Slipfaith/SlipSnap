# AGENT.md — SlipSnap

Руководство для AI-агентов, работающих с этим репозиторием.

## Что это

**SlipSnap v3.1** — десктопное приложение на Python/PySide6 для захвата скриншотов и коротких видео с встроенным редактором. Windows-only. Запускается из трея.

## Стек

| Слой | Технология |
|------|-----------|
| UI | PySide6 (Qt 6) |
| Изображения | Pillow (PIL) |
| Захват экрана | mss |
| OCR | pytesseract + Tesseract |
| Видео | ffmpeg (внешний бинарник) |
| Win32 API | pywin32 (`win32gui`, `win32com`, `win32con`) |
| Сборка | PyInstaller + Inno Setup (`.iss`) |

## Структура

```
main.py                   # Точка входа. Версия — APP_VERSION здесь.
gui.py                    # App (QSystemTrayIcon) + оверлей выделения области
logic.py                  # Конфиг (~/.slipsnap_config.json), история, снимок экрана
design_tokens.py          # Palette, Metrics, Typography — все UI-константы
clipboard_utils.py        # Копирование PIL Image в буфер
icons.py                  # SVG-иконки, генерируемые программно
collage.py                # Коллаж из истории снимков
meme_library.py           # Библиотека мемов (GIF/PNG)
meme_gif_workflow.py      # Вставка GIF-мемов в холст
ocr.py                    # Обёртка над pytesseract
upload_service.py         # Загрузка файла на внешний сервер
video_capture.py          # Захват видео с экрана
video_encoding.py         # Кодирование через ffmpeg

editor/
  editor_window.py        # EditorWindow (QMainWindow) — главное окно редактора
  editor_logic.py         # EditorLogic — сохранение, именование файлов
  editor/ui/
    canvas.py             # Canvas (QGraphicsView) — холст, инструменты, drag-and-drop
    toolbar_factory.py    # Панель инструментов
    styles.py             # ModernColors и QSS-строки
    color_widgets.py      # Виджеты выбора цвета
    high_quality_pixmap_item.py  # QGraphicsPixmapItem с HQ рендерингом
    zoom_lens_item.py     # Лупа на холсте
    meme_library_dialog.py
    icon_factory.py
    window_utils.py
    selection_items.py
  editor/tools/           # Инструменты рисования (base_tool.py → конкретные)
    pencil_tool.py
    shape_tools.py        # RectangleTool, EllipseTool
    blur_tool.py
    eraser_tool.py
    line_arrow_tool.py
    selection_tool.py
  undo_commands.py        # QUndoCommand-субклассы (Add, Move, Resize, …)
  text_tools.py           # EditableTextItem, TextManager
  ocr_overlay.py          # Оверлей выделения для OCR
  image_utils.py          # images_from_mime, gif_*_from_mime
  series_capture.py       # Серийный захват (несколько снимков подряд)

pyqtkeybind/              # Локальная либа для глобальных хоткеев (Win32)
tests/                    # pytest-тесты
```

## Ключевые классы

### `App` (gui.py)
Системный трей. Перехватывает глобальные хоткеи через `pyqtkeybind`. При захвате показывает `SelectionOverlay` → передаёт `QImage` в `EditorWindow`.

### `EditorWindow` (editor/editor_window.py)
Главное окно редактора. Содержит `Canvas` и `EditorLogic`. Атрибут `self.logic` — всегда `EditorLogic`.

### `Canvas` (editor/ui/canvas.py)
`QGraphicsView` с `QGraphicsScene`. Весь рисунок, drag-and-drop, анимации, инструменты — здесь. Сигнал `imageDropped` — когда пользователь дропает изображение НА холст.

### `EditorLogic` (editor/editor_logic.py)
Отвечает за:
- `save_image(parent)` — диалог сохранения
- `_next_snap_name(directory, ext)` — следующий свободный `snap_NN.ext` в папке
- `next_snap_filename_for_directory(dir, ext)` — публичный API для именования при drag
- `_last_save_directory` — последняя папка сохранения (персистится в конфиг)

## Конфигурация

Файл: `~/.slipsnap_config.json`
Загрузка: `logic.load_config()` → `DEFAULT_CONFIG` в `logic.py` (там же все ключи)
Сохранение: `logic.save_config(cfg)`

Версия приложения меняется **только** в `main.py` → `APP_VERSION`.

## Именование файлов при сохранении

Формат: `snap_01.png`, `snap_02.png`, …
Логика в `EditorLogic._next_snap_name()`:
1. Сканирует директорию на `snap_*.{png,jpg,jpeg,gif}`
2. Берёт максимальный номер → +1, zero-pad до 2 цифр

## Drag-and-drop из холста в проводник

`Canvas._start_external_drag()` → `Canvas._next_drag_filename()` → `Canvas._detect_external_drop_directory()`

Детекция целевой папки Explorer в 4 этапа:
1. Окно под курсором в момент начала дрэга
2. Единственное открытое окно Explorer
3. Верхнее по Z-order окно Explorer (не SlipSnap)
4. Рабочий стол (Progman/WorkerW)

После успешного дропа (`Qt.CopyAction`) обновляет `logic._last_save_directory`.

## История снимков

`HISTORY_DIR = %TEMP%/slipsnap_history/` — PNG-файлы последних снимков.
Используется для коллажа (`collage.py`).

## Тесты

```bash
pytest tests/
```

Тесты не мокают файловую систему — используют `tmp_path` фикстуру pytest.
Тесты не требуют GUI (используют `QApplication` через фикстуры где нужно).

## Сборка

```bash
pyinstaller SlipSnap.spec      # собирает exe
# затем Inno Setup с installer/SlipSnap.iss для инсталлятора
```

## Переменные окружения

| Переменная | Назначение |
|-----------|-----------|
| `SLIPSNAP_LOG_LEVEL` | Уровень логирования (по умолч. `INFO`) |

Лог пишется в `%TEMP%/SlipSnap.log`.

## Частые задачи

**Поменять версию** → `main.py`, строка `APP_VERSION`

**Добавить инструмент рисования** → создать класс в `editor/tools/`, наследовать от `BaseTool`, зарегистрировать в `Canvas` и `toolbar_factory.py`

**Добавить настройку в конфиг** → добавить ключ в `DEFAULT_CONFIG` в `logic.py`

**Добавить кнопку в тулбар редактора** → `editor/ui/toolbar_factory.py`

**Изменить цвет/размер UI** → `design_tokens.py` (не хардкодить в виджетах)
