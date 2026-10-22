<!-- -*- coding: utf-8 -*- -->
# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and follows Semantic Versioning.

---

## Русский

### [Unreleased]

- Подготовка к следующим улучшениям стабильности и UX.

### [3.4.0] - 2026-10-22

#### Added

- Инструмент «Ножницы» (X) в редакторе: проведите разрез через один или несколько снимков, затем ПКМ по куску → «Удалить кусок». На его месте остаётся прозрачность, а край выглядит как рваная бумага (кромка, волокна, мягкая тень). Разрезы и удаление отменяются через Ctrl+Z.

#### Changed

- После удаления куска ножницами редактор сам возвращается к инструменту выделения.
- Иконка инструмента выделения теперь — стрелка-курсор.

#### Fixed

- Выделение области для скриншота можно вести через несколько мониторов с разным масштабом; снимок склеивается в одно изображение.
- Копирование и сохранение из редактора больше не замыливают снимок на экранах с масштабом больше 100%.
- Плашка записи видео (кадры и время) больше не попадает в видео на Windows 10: она размещается вне записываемой области.
- Из requirements.txt убрана лишняя зависимость pyqtkeybind, которая тянула PyQt5.

### [3.3.3] - 2026-10-22

#### Fixed

- Выделение области экрана совпадает с курсором на конфигурациях из нескольких мониторов с разным масштабом (DPI).

### [3.3.2] - 2026-09-11

#### Added

- Самопроверка упакованного приложения и тесты доступности настроек AI OCR.

#### Changed

- Улучшено контекстное меню OCR: настройки API-ключей открываются по ПКМ без изменения основного действия кнопки.
- Обновлены метаданные, иконка и сборочные настройки Windows-версии.

#### Fixed

- Автозапуск в установщике создаётся для текущего пользователя.
- Ошибки открытия настроек или запуска OCR теперь показываются пользователю и записываются в журнал.

### [3.2.0] - 2026-04-08

#### Added

- Новые автотесты:
  - `tests/test_logic_paths.py`
  - `tests/test_textbox_interactions.py`
  - `tests/test_meme_dialog_delete.py::test_gif_preview_avoids_direct_file_binding`

#### Changed

- Библиотека мемов перенесена в пользовательскую директорию приложения (`LOCALAPPDATA/SlipSnap/memes`) с fallback и миграцией из legacy-пути `%TEMP%/slipsnap_memes`.
- Улучшено редактирование текста на холсте: корректное завершение редактирования при смене инструмента/клике вне текста и стабильная работа placeholder.
- Превью GIF в библиотеке теперь работает через буфер в памяти вместо прямой привязки к файлу, что снижает блокировки при удалении и переименовании.

#### Fixed

- Удалены тестовые артефакты из репозитория и добавлен ignore-шаблон для временных директорий `tests/meme_migration_*/`.

### [3.0.0] - 2026-03-01

#### Added

- Централизация версии и метаданных приложения в `main.py`:
  - `APP_NAME`
  - `APP_VERSION`
  - `APP_DESCRIPTION`
  - `APP_AUTHOR`
- Быстрый шаринг из редактора:
  - кнопка `Поделиться ссылкой (24ч)` в верхнем тулбаре;
  - экспорт текущего изображения (PNG/GIF), загрузка в хостинг, копирование ссылки в буфер.
- Новый `upload_service.py` с фоновым `UploadWorker(QThread)` для неблокирующего UI.
- Отдельная иконка шаринга `make_icon_share()`.
- Новые автотесты:
  - `tests/test_logic_share_config.py`
  - `tests/test_upload_service.py`

#### Changed

- Улучшен GIF-workflow редактора:
  - GIF из буфера/библиотеки вставляются как анимированные элементы сцены;
  - при GIF-контенте и анимациях корректно сохраняется анимированный GIF.
- Улучшена работа видео-захвата и сценариев экспорта MP4/GIF.
- Обновлена документация `README.md` (RU/EN) и добавлен `github.md` с краткими release notes.

#### Fixed

- Исправлены silent-failure сценарии в критичных ветках GIF/clipboard/video.
- Улучшена диагностика и логирование в чувствительных пользовательских сценариях.
- Доработано поведение UI при шаринге (чёткие статусы, обработка ошибок, cleanup временных файлов).

---

## English

### [Unreleased]

- Preparations for upcoming stability and UX improvements.

### [3.4.0] - 2026-10-22

#### Added

- Scissors tool (X) in the editor: draw a cut across one or several images, then right-click a piece → "Удалить кусок". It leaves transparency behind with a torn-paper edge (paper rim, fibres, soft shadow). Cuts and deletions can be undone with Ctrl+Z.

#### Changed

- After deleting a piece with the scissors, the editor switches back to the selection tool.
- The selection tool icon is now a pointer arrow.

#### Fixed

- A screenshot selection can now span monitors with different scaling; the capture is stitched into one image.
- Copying and saving from the editor no longer blurs the image on screens scaled above 100%.
- The video recording HUD (frames and time) no longer ends up in videos on Windows 10: it is placed outside the recorded area.
- Removed the redundant pyqtkeybind dependency from requirements.txt, which pulled in PyQt5.

### [3.3.3] - 2026-10-22

#### Fixed

- Screen selection now lines up with the cursor on multi-monitor setups with mixed DPI scaling.

### [3.3.2] - 2026-09-11

#### Added

- Packaged-app self-check and AI OCR settings access tests.

#### Changed

- Improved OCR context menu: API key settings open on right-click without changing the button's primary action.
- Updated Windows build metadata, icon, and packaging settings.

#### Fixed

- The installer creates the autostart entry for the current user.
- Failures opening OCR settings or starting OCR are now shown to the user and logged.

### [3.2.0] - 2026-04-08

#### Added

- New automated tests:
  - `tests/test_logic_paths.py`
  - `tests/test_textbox_interactions.py`
  - `tests/test_meme_dialog_delete.py::test_gif_preview_avoids_direct_file_binding`

#### Changed

- Meme storage moved to app data (`LOCALAPPDATA/SlipSnap/memes`) with fallback and automatic migration from legacy `%TEMP%/slipsnap_memes`.
- Improved canvas text-editing flow: proper edit finalization on tool switch/outside click and more stable placeholder behavior.
- GIF previews in the meme library now use in-memory buffers instead of direct file binding, reducing file-lock issues during delete/rename.

#### Fixed

- Removed test artifacts from the repository and added an ignore pattern for temporary `tests/meme_migration_*/` directories.

### [3.0.0] - 2026-03-01

#### Added

- Version/app metadata centralized in `main.py`:
  - `APP_NAME`
  - `APP_VERSION`
  - `APP_DESCRIPTION`
  - `APP_AUTHOR`
- Fast editor sharing flow:
  - `Share link (24h)` action in top toolbar;
  - current export (PNG/GIF) upload and clipboard URL copy.
- New `upload_service.py` with background `UploadWorker(QThread)` to keep UI responsive.
- Dedicated share icon `make_icon_share()`.
- New automated tests:
  - `tests/test_logic_share_config.py`
  - `tests/test_upload_service.py`

#### Changed

- Improved editor GIF workflow:
  - animated GIF paste from clipboard/library;
  - proper animated GIF export when scene contains GIF/animated content.
- Improved video capture and MP4/GIF export scenarios.
- Updated docs in `README.md` (RU/EN) and added concise release notes in `github.md`.

#### Fixed

- Fixed silent-failure paths in critical GIF/clipboard/video flows.
- Improved diagnostics/logging in sensitive user-facing scenarios.
- Improved share UX behavior (status feedback, error handling, temp-file cleanup).
