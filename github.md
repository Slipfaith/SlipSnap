<!-- -*- coding: utf-8 -*- -->
# SlipSnap 3.0 — Release Notes

## Русский (кратко)

**SlipSnap 3.0** — релиз с акцентом на GIF-workflow, видео и быстрый шаринг.

### Главное

- Новый шаринг из редактора: **Поделиться ссылкой (24ч)**.
- Улучшенный GIF-пайплайн:
  - вставка анимированных GIF из буфера и библиотеки;
  - экспорт анимированного GIF при наличии анимаций/GIF-контента.
- Zoom Lens как полноценный объект сцены.
- Анимации объектов (`Draw`, `Pulse`) через контекстное меню.
- Обновлённая библиотека мемов:
  - анимированные превью;
  - удаление, переименование, открытие папки;
  - сохранение размера окна.
- Улучшения видео-захвата и multi-monitor/DPI-координат.

### Технически

- Централизация версии и метаданных приложения в `main.py`.
- Расширенное покрытие тестами ключевых сценариев (GIF, video, zoom lens, share).

---

## English (short)

**SlipSnap 3.0** focuses on GIF workflow, video capture, and quick sharing.

### Highlights

- New editor action: **Share link (24h)**.
- Improved GIF pipeline:
  - animated GIF paste from clipboard and meme library;
  - animated GIF export when scene contains GIF/animated objects.
- Zoom Lens as a first-class scene object.
- Object animations (`Draw`, `Pulse`) via context menu.
- Meme library upgrades:
  - animated previews;
  - delete/rename/open-folder actions;
  - persistent dialog size.
- Better video capture flow and multi-monitor/DPI coordinate handling.

### Technical notes

- App metadata/version centralized in `main.py`.
- Broader automated test coverage for GIF/video/zoom/share flows.
