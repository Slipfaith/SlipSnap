# GIF Manual QA Checklist

Date: 2026-02-28  
Scope: GIF save flow, meme library integration, GIF copy/paste behavior.

## 1) Save Flow

- [ ] Start video capture and stop normally.
- [ ] In save dialog select `GIF`.
- [ ] Check "Добавить в библиотеку мемов".
- [ ] Save file.
- Expected:
  - GIF file is created.
  - GIF appears in meme library.
  - No delayed post-save popup appears.

## 2) Save Flow (MP4)

- [ ] Start video capture and stop normally.
- [ ] In save dialog select `MP4`.
- [ ] Verify "Добавить в библиотеку мемов" is disabled.
- [ ] Save file.
- Expected:
  - MP4 file is created.
  - Nothing is imported into meme library.

## 3) Meme Library GIF Preview

- [ ] Open meme library with multiple GIFs.
- [ ] Scroll list.
- Expected:
  - GIF thumbnails animate.
  - GIF thumbnails show `GIF` badge.
  - Off-screen GIFs pause.
  - Broken GIFs show fallback preview (`GIF ERR`).

## 4) Copy GIF -> Paste in Editor

- [ ] In meme library select GIF and press `Ctrl+C`.
- [ ] In editor press `Ctrl+V`.
- Expected:
  - Inserted object stays animated (not static first frame).
  - Object supports move/select/scale/delete.
  - Undo/redo works.

## 5) Copy GIF -> External App

- [ ] In meme library select GIF and press `Ctrl+C`.
- [ ] Paste into at least one external app (chat, browser, or messenger).
- Expected:
  - GIF/file payload is accepted by target app.
  - If target app does not support GIF clipboard payload, behavior is platform/app-specific.

## 6) Regression: PNG/JPG

- [ ] Copy PNG/JPG meme from library and paste into editor.
- [ ] Copy editor result and paste into target apps.
- Expected:
  - Existing PNG/JPG behavior remains unchanged.

