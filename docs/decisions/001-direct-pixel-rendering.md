# 001 — Direct Pixel Rendering Pipeline

## Context

Video visualization requires rendering 30fps frames, both for real-time player
playback and for export. Matplotlib's `FuncAnimation` redraws the entire figure
each frame — axes, labels, colorbars, data — which is far too slow for real-time
use and produces unnecessarily large video files due to re-encoding identical
static regions.

## Decision

Bypass matplotlib for per-frame updates. Capture the static "chrome" (axes,
labels, borders) once into a numpy RGB array, then use a shift-and-paint
pipeline that operates directly on the frame buffer:

1. Shift existing data pixels left by the scroll delta
2. Paint only the newly revealed strip (spectrogram colormap + amplitude fill)
3. Composite axis overlays, position lines, and time text on top
4. Restore overlay regions before the next frame to maintain a clean buffer

The pipeline lives in `VideoVisualization.prepare_direct_render()` and
`render_frame_direct()` in `visualization/video.py`.

## Rationale

This achieves ~10-50x speedup over matplotlib's per-frame redraw. The frame
buffer is a contiguous RGB numpy array, so `.tobytes()` for FFmpeg pipe writes
is a zero-copy operation. The incremental scroll means most pixels are simply
shifted, not recomputed — only the thin new strip at the trailing edge requires
actual rendering work each frame.
