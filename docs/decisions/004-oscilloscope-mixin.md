# 004 — Oscilloscope as a Mixin Class

## Context

The oscilloscope overlay shows a trigger-stabilized raw audio waveform per
channel, with automatic pulse detection that switches window length between
tonal and pulsed content. It needs deep access to `VideoVisualization` instance
state: frame buffer, data regions, amplitude colors, spectrogram times, channel
layout, font rendering state, and DPI scaling.

## Decision

Implement the oscilloscope as a mixin class (`OscilloscopeMixin` in
`visualization/oscilloscope.py`) that `VideoVisualization` inherits from
alongside `Visualization`.

## Rationale

The oscilloscope methods share 10+ pieces of instance state with the host
visualization. A standalone utility class or module would require passing all
of this as parameters to every function call, creating an unwieldy API. The
mixin keeps the oscilloscope code cleanly separated (~450 lines) while giving
it natural access to the host's instance state through `self`.

The mixin initializes its own state in `_dr_osc_init()` (called from
`prepare_direct_render()`) and draws via `_dr_osc_draw()` (called per-frame).
It adds no public API — all methods are prefixed with `_dr_osc_` or `_osc_`.
