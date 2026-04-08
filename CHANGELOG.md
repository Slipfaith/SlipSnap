<!-- -*- coding: utf-8 -*- -->
# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and follows Semantic Versioning.

---

## Русский

### [Unreleased]

- Подготовка к следующим улучшениям стабильности и UX.

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
