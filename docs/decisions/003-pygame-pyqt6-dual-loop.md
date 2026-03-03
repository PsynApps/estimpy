# 003 — Pygame-ce for Audio, PyQt6 for GUI

## Context

The player needs both audio playback with per-channel volume control and a
native GUI with visualization rendering. Qt has `QMediaPlayer` but it lacks
fine-grained per-channel mixing. Pygame-ce has a mature SDL2 mixer but no
native windowing system suitable for complex UI controls.

## Decision

Use two frameworks side by side:
- **Pygame-ce** (`player/audio.py`): Audio mixing via `pygame.mixer`, with
  per-channel stereo panning and volume ramping in daemon threads
- **PyQt6** (`player/window.py`): Window management, controls, frame display
  via `QImage`, keyboard/mouse input

The two loops coexist — PyQt6's `QApplication.exec()` drives the event loop,
while a `QTimer` at the target framerate calls the render pipeline and polls
pygame's audio state.

## Rationale

This avoids reimplementing audio mixing in Qt and leverages pygame's mature
SDL2 mixer for low-latency playback. The coupling between the two is minimal:
`player/audio.py` exposes module-level functions (`play`, `stop`, `set_volume`,
`get_time`) that the Qt window calls during timer ticks.

Trade-off: `player/audio.py` uses module-level globals instead of a class
instance, which precludes multiple simultaneous players. This is acceptable
since the application is single-player by design.
