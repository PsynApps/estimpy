"""Video visualization with direct render pipeline.

Contains VideoVisualization which extends Visualization with time-windowed
sliding view, frame-by-frame rendering, and the shift-and-paint pipeline
that bypasses matplotlib for per-frame updates. Inherits oscilloscope
overlay capability from OscilloscopeMixin.
"""

import math
import time
import typing

import estimpy as es
import matplotlib
import matplotlib.animation
import matplotlib.colors
import matplotlib.gridspec
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from estimpy.visualization.base import AxisTypes, Visualization, VisualizationMode
from estimpy.visualization.oscilloscope import OscilloscopeMixin


class VideoVisualization(Visualization, OscilloscopeMixin):
    def __init__(self, es_audio: es.audio.Audio = None, fps: float = None, frames: range = None):
        super().__init__(es_audio=es_audio)

        self._animation = None  # type: matplotlib.animation.FuncAnimation | None
        self._fps = es.cfg['visualization.video.export.fps'] if fps is None else fps
        self._frames = range(math.floor(es_audio.length * self.fps)) if frames is None else frames
        self._frame = 0

        # Length of video windows
        # Padding ensures there sufficient data to fill the window without glitches (does not need to be configurable)
        self._window_padding_factor = 1.1
        self._window_length = es.cfg['visualization.video.export.window-length']

        self.__amplitude_window_length = None
        self.__spectrogram_window_length = None
        self.__precolored_spectrograms = None


    @property
    def animation(self) -> matplotlib.animation.FuncAnimation | None:
        if self._animation is None:
            self._set_animation()

        return self._animation

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frames(self) -> range:
        return self._frames

    @property
    def _amplitude_window_length(self):
        if self.__amplitude_window_length is None:
            self.__amplitude_window_length = self.i_amplitude(
                self._window_padding_factor * self._window_length)

        return self.__amplitude_window_length

    @property
    def _spectrogram_window_length(self):
        if self.__spectrogram_window_length is None:
            self.__spectrogram_window_length = self.i_spectrogram(
                self._window_padding_factor * self._window_length)

        return self.__spectrogram_window_length

    @property
    def _precolored_spectrograms(self):
        if self.__precolored_spectrograms is None:
            self.__precolored_spectrograms = {}
            norm = matplotlib.colors.Normalize(
                vmin=-es.cfg['visualization.style.spectrogram.dynamic-range'], vmax=0)
            for channel_id in range(self.es_audio.channels):
                style_cfg = self._get_spectrogram_style_cfg(channel_id)
                cmap = matplotlib.colormaps[style_cfg['color-map']]
                self.__precolored_spectrograms[channel_id] = cmap(
                    norm(self.spectrogram.spectrogram_data[channel_id])).astype(np.float32)

        return self.__precolored_spectrograms

    def load(self, es_audio: es.audio.Audio):
        if es_audio is None:
            return

        super().load(es_audio=es_audio)

        self._animation = None
        self._frames = range(math.floor(es_audio.length * self.fps))
        self.__precolored_spectrograms = None

    def make_figure(self, skip_initial_frame=False):
        super().make_figure()
        if not skip_initial_frame:
            self.make_frame(0)

    def make_frame(self, frame):
        if self._handles['figure'] is None:
            return

        self._frame = frame
        t = self._frame_to_time(frame)

        for position_line in self._handles['position_lines']:
            position_line.set_xdata([t])

        axes_xlim = self._get_window_range(
            t=t,
            total_length=self.es_audio.length,
            window_length=self._window_length)

        i_amplitude_min, i_amplitude_max = self._get_window_range(
            t=self.i_amplitude(t),
            total_length=len(self.peak_envelope.times) - 1,
            window_length=self._amplitude_window_length,
            round_bounds=True)

        # Update the amplitude
        for channel_id, _ in self._channel_layout:
            axes_style_cfg = self._get_amplitude_style_cfg(channel_id)

            axes_key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=channel_id)

            self._handles['axes'][axes_key].set_xlim(axes_xlim)

            # Peak envelope
            peak_x = self.peak_envelope.times[i_amplitude_min:i_amplitude_max]
            peak_y = es.analysis.Envelope.pad_envelope_data(
                self.peak_envelope.envelope_data[channel_id, (i_amplitude_min + 1):(i_amplitude_max - 1)])
            peak_xy = np.column_stack([peak_x, peak_y])

            if channel_id in self._handles['amplitude_peak_fills']:
                self._handles['amplitude_peak_fills'][channel_id].set_xy(peak_xy)
            else:
                self._handles['amplitude_peak_fills'][channel_id] = self._handles['axes'][axes_key].fill(
                    peak_x, peak_y, color=axes_style_cfg['base-color'])[0]

            # RMS envelope
            if es.cfg['visualization.style.amplitude.show-rms']:
                rms_x = self.rms_envelope.times[i_amplitude_min:i_amplitude_max]
                rms_y = es.analysis.Envelope.pad_envelope_data(
                    self.rms_envelope.envelope_data[channel_id, (i_amplitude_min + 1):(i_amplitude_max - 1)])
                rms_xy = np.column_stack([rms_x, rms_y])

                if channel_id in self._handles['amplitude_rms_fills']:
                    self._handles['amplitude_rms_fills'][channel_id].set_xy(rms_xy)
                else:
                    self._handles['amplitude_rms_fills'][channel_id] = self._handles['axes'][axes_key].fill(
                        rms_x, rms_y, color=axes_style_cfg['rms-color'])[0]

        i_spectrogram_min, i_spectrogram_max = self._get_window_range(
            t=self.i_spectrogram(t),
            total_length=len(self.spectrogram.times) - 1,
            window_length=self._spectrogram_window_length,
            round_bounds=True)

        for channel_id, _ in self._channel_layout:
            axes_key = self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)

            self._handles['axes'][axes_key].set_xlim(axes_xlim)

            spec_data = self._precolored_spectrograms[channel_id][:, i_spectrogram_min:i_spectrogram_max, :]
            spec_extent = [self.spectrogram.times[i_spectrogram_min],
                           self.spectrogram.times[i_spectrogram_max],
                           self.spectrogram.frequency_min,
                           self.spectrogram.frequency_max]

            if channel_id in self._handles['spectrogram_images']:
                self._handles['spectrogram_images'][channel_id].set_data(spec_data)
                self._handles['spectrogram_images'][channel_id].set_extent(spec_extent)
            else:
                self._handles['spectrogram_images'][channel_id] = self._handles['axes'][axes_key].imshow(
                    spec_data, aspect='auto', origin='lower',
                    extent=spec_extent)

        self._update_time_text()

        return self._handles['figure']

    def resize_figure(self, width=None, height=None, dpi=None) -> typing.Tuple[float, float] | None:
        if self._handles['figure'] is None:
            return

        width_scale_factor, height_scale_factor = super().resize_figure(width=width, height=height, dpi=dpi)

        for position_line in self._handles['position_lines']:
            position_line.set_linewidth(position_line.get_linewidth() * width_scale_factor)

        return width_scale_factor, height_scale_factor

    def prepare_direct_render(self, profiling: bool = False):
        """One-time setup for direct frame rendering (bypasses matplotlib per-frame)."""
        fig = self._handles['figure']
        fig.canvas.draw()
        fig_width, fig_height = fig.canvas.get_width_height()
        self._pt_to_px = fig.dpi / 72  # points-to-pixels conversion factor

        # Identify data subplot keys (only for displayed channels)
        self._dr_data_axes_keys = []
        for channel_id, _ in self._channel_layout:
            self._dr_data_axes_keys.append(
                self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=channel_id))
            self._dr_data_axes_keys.append(
                self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id))

        # --- Capture 1: Chrome image (no dynamic elements) ---
        self._set_dynamic_elements_visible(False)
        fig.canvas.draw()
        self._chrome_image = np.array(fig.canvas.buffer_rgba())[:, :, :3].copy()

        # --- Capture 2: Axis overlay (data subplot backgrounds transparent) ---
        orig_fig_facecolor = fig.patch.get_facecolor()
        orig_facecolors = {}
        fig.patch.set_facecolor((0, 0, 0, 0))
        for key in self._dr_data_axes_keys:
            ax = self._handles['axes'][key]
            orig_facecolors[key] = ax.get_facecolor()
            ax.set_facecolor((0, 0, 0, 0))

        fig.canvas.draw()
        axis_overlay_rgba = np.array(fig.canvas.buffer_rgba())
        self._axis_overlay = axis_overlay_rgba[:, :, :3].copy()
        self._axis_overlay_alpha = axis_overlay_rgba[:, :, 3].copy()

        # Restore facecolors
        fig.patch.set_facecolor(orig_fig_facecolor)
        for key in self._dr_data_axes_keys:
            self._handles['axes'][key].set_facecolor(orig_facecolors[key])
        self._set_dynamic_elements_visible(True)

        # --- Compute subplot pixel regions ---
        self._data_regions = {}
        for key in self._dr_data_axes_keys:
            bbox = self._handles['axes'][key].get_position()
            x0 = int(round(bbox.x0 * fig_width))
            y0 = int(round((1 - bbox.y1) * fig_height))
            x1 = int(round(bbox.x1 * fig_width))
            y1 = int(round((1 - bbox.y0) * fig_height))
            self._data_regions[key] = (x0, y0, x1, y1)

        self._scrub_regions = {}
        for channel_id, _ in self._scrub_channel_layout:
            key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE_SCRUB, channel=channel_id)
            bbox = self._handles['axes'][key].get_position()
            x0 = int(round(bbox.x0 * fig_width))
            y0 = int(round((1 - bbox.y1) * fig_height))
            x1 = int(round(bbox.x1 * fig_width))
            y1 = int(round((1 - bbox.y0) * fig_height))
            self._scrub_regions[key] = (x0, y0, x1, y1)

        # --- Position line width ---
        if self._handles['position_lines']:
            lw_pt = self._handles['position_lines'][0].get_linewidth()
            self._position_line_width_px = max(1, int(round(lw_pt * self._pt_to_px)))
        else:
            self._position_line_width_px = 1

        line_color = matplotlib.colors.to_rgb(es.cfg['visualization.style.video.position-line-color'])
        self._position_line_color = (np.array(line_color) * 255).astype(np.uint8)

        # --- Time text rendering setup ---
        self._dr_time_enabled = self._time_enabled()
        self._dr_time_position_top = (self._time_position() == 'top')

        if self._dr_time_enabled and self._handles['time'] is not None:
            time_fontsize_pt = self._handles['time'].get_fontsize()
            self._dr_time_font_size_px = max(1, int(round(time_fontsize_pt * self._pt_to_px)))

            font_file = es.cfg['visualization.style.font.text.file']
            face_index = es.cfg['visualization.style.font.text.face-index']
            self._dr_time_font = ImageFont.truetype(font_file, self._dr_time_font_size_px, index=face_index)

            time_color_rgb = matplotlib.colors.to_rgb(es.cfg['visualization.style.axes.color'])
            self._dr_time_color = tuple(int(c * 255) for c in time_color_rgb)

            border_color_rgb = matplotlib.colors.to_rgb(es.cfg['visualization.style.font.text.border-color'])
            self._dr_time_border_color = tuple(int(c * 255) for c in border_color_rgb)
            self._dr_time_border_width = max(1, int(round(self._text_border_width * self._pt_to_px)))

        # --- Pre-compute axis overlay masks for data regions (for efficient compositing) ---
        self._axis_overlay_masks = {}
        for key in self._dr_data_axes_keys:
            x0, y0, x1, y1 = self._data_regions[key]
            mask = self._axis_overlay_alpha[y0:y1, x0:x1] > 0
            self._axis_overlay_masks[key] = mask

        # Store figure dimensions
        self._dr_fig_width = fig_width
        self._dr_fig_height = fig_height

        # --- Shift-and-paint state ---

        # Scroll dynamics
        # Use the first data region to get panel width (all panels span full figure width)
        first_key = self._dr_data_axes_keys[0]
        dr_x0, _, dr_x1, _ = self._data_regions[first_key]
        self._dr_panel_width = dr_x1 - dr_x0
        self._dr_pixels_per_second = self._dr_panel_width / self._window_length
        self._dr_never_scrolls = self.es_audio.length <= self._window_length

        # Per-channel colormap objects (for on-demand spectrogram coloring)
        self._dr_spec_norm = matplotlib.colors.Normalize(
            vmin=-es.cfg['visualization.style.spectrogram.dynamic-range'], vmax=0)
        self._dr_spec_cmaps = {}
        for ch, _ in self._channel_layout:
            style_cfg = self._get_spectrogram_style_cfg(ch)
            self._dr_spec_cmaps[ch] = matplotlib.colormaps[style_cfg['color-map']]

        # Cached amplitude y-max per channel
        self._dr_amp_y_max = {}
        for ch, _ in self._channel_layout:
            self._dr_amp_y_max[ch] = self._get_amplitude_y_max(ch)
        self._dr_show_rms = es.cfg['visualization.style.amplitude.show-rms']
        self._dr_amp_bg_rgb = {}
        self._dr_amp_peak_rgb = {}
        self._dr_amp_rms_rgb = {}
        for ch, _ in self._channel_layout:
            style_cfg = self._get_amplitude_style_cfg(ch)
            self._dr_amp_bg_rgb[ch] = (np.array(matplotlib.colors.to_rgb(style_cfg['background-color'])) * 255).astype(np.uint8)
            self._dr_amp_peak_rgb[ch] = (np.array(matplotlib.colors.to_rgb(style_cfg['base-color'])) * 255).astype(np.uint8)
            if self._dr_show_rms:
                self._dr_amp_rms_rgb[ch] = (np.array(matplotlib.colors.to_rgb(style_cfg['rms-color'])) * 255).astype(np.uint8)

        # Invert flags per panel
        self._dr_invert = {}
        for ch, inv in self._channel_layout:
            self._dr_invert[self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=ch)] = inv
            self._dr_invert[self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=ch)] = inv

        # Direct references to data arrays (avoid property lookups per frame)
        self._dr_peak_times = self.peak_envelope.times
        self._dr_peak_data = self.peak_envelope.envelope_data
        self._dr_rms_times = self.rms_envelope.times if self._dr_show_rms else None
        self._dr_rms_data = self.rms_envelope.envelope_data if self._dr_show_rms else None
        self._dr_spec_times = self.spectrogram.times

        # Pre-compute axis overlay fancy indices (for efficient save/restore)
        self._dr_overlay_indices = {}
        self._dr_overlay_values = {}
        for key in self._dr_data_axes_keys:
            x0, y0, x1, y1 = self._data_regions[key]
            mask = self._axis_overlay_masks[key]
            if mask.any():
                ys, xs = np.where(mask)
                self._dr_overlay_indices[key] = (ys + y0, xs + x0)
                self._dr_overlay_values[key] = self._axis_overlay[y0:y1, x0:x1][mask].copy()

        # Note: _axis_overlay and _axis_overlay_alpha are kept alive
        # to support re-rendering window time labels on zoom changes

        # Initialize persistent frame buffer and state
        self._dr_frame_buffer = self._chrome_image.copy()
        self._dr_buffer_initialized = False
        self._dr_prev_window_min = None
        self._dr_scroll_accumulator = 0.0
        self._dr_saved_regions = []
        self._dr_overlay_underlay = {}
        self._dr_time_text_cache = {}

        # Free precolored spectrograms to save memory (export path uses on-demand colormap)
        for ch in self._handles['spectrogram_images']:
            self._handles['spectrogram_images'][ch].set_data(np.zeros((1, 1, 4)))
        self.__precolored_spectrograms = None

        # Initialize oscilloscope state (from OscilloscopeMixin)
        self._dr_osc_init(fig)

        # Profiling
        self._dr_profiling = profiling
        if self._dr_profiling:
            self._dr_profile_interval = 100
            self._dr_profile_frame_count = 0
            self._dr_profile_times = {
                'restore_overlays': 0.0,
                'restore_axis': 0.0,
                'shift_panels': 0.0,
                'paint_strips': 0.0,
                'save_axis': 0.0,
                'apply_axis': 0.0,
                'save_overlays': 0.0,
                'draw_oscilloscope': 0.0,
                'draw_lines': 0.0,
                'draw_time': 0.0,
                'total_render': 0.0,
            }

    def _dr_print_profile(self):
        """Print profiling summary and reset accumulators."""
        n = self._dr_profile_frame_count
        if n == 0:
            return
        print(f'\n--- Render profile ({n} frames) ---')
        total = self._dr_profile_times['total_render']
        for key, val in self._dr_profile_times.items():
            avg_ms = (val / n) * 1000
            pct = (val / total * 100) if total > 0 else 0
            print(f'  {key:20s}: {avg_ms:7.2f} ms/frame  ({pct:5.1f}%)')
        print(f'  {"avg fps":20s}: {n / total:.1f}' if total > 0 else '')
        print()
        # Reset
        self._dr_profile_frame_count = 0
        for key in self._dr_profile_times:
            self._dr_profile_times[key] = 0.0

    def render_frame_direct(self, frame) -> np.ndarray:
        """Render a single frame as an RGB numpy array using shift-and-paint optimization."""
        _profiling = self._dr_profiling
        if _profiling:
            t0_total = time.perf_counter()

        self._frame = frame
        t = self._frame_to_time(frame)

        window_min, window_max = self._get_window_range(
            t=t, total_length=self.es_audio.length, window_length=self._window_length)
        axes_xlim = (window_min, window_max)

        if not self._dr_buffer_initialized:
            # Full re-render of all panels (first frame or after zoom change).
            # Restore any previous overlays first -- position lines drawn on the
            # scrub panels are baked into the frame buffer and must be erased
            # before re-rendering, since scrub panels are not repainted here.
            self._dr_restore_overlay_regions()
            self._dr_restore_axis_underlay()
            self._dr_render_full_panels(window_min, window_max)
            self._dr_buffer_initialized = True
        else:
            # Subsequent frames: restore previous overlays, then shift or re-render
            if _profiling:
                t0 = time.perf_counter()
            self._dr_restore_overlay_regions()
            if _profiling:
                self._dr_profile_times['restore_overlays'] += time.perf_counter() - t0

                t0 = time.perf_counter()
            self._dr_restore_axis_underlay()
            if _profiling:
                self._dr_profile_times['restore_axis'] += time.perf_counter() - t0

            shift_pixels = 0
            if not self._dr_never_scrolls and window_min != self._dr_prev_window_min:
                shift_pixels = self._dr_compute_scroll(window_min)

            if shift_pixels == -1:
                # Discontinuous jump -- full re-render
                self._dr_render_full_panels(window_min, window_max)
            elif shift_pixels > 0:
                # Incremental scroll -- shift and paint new strip
                if _profiling:
                    t0 = time.perf_counter()
                self._dr_shift_panels(shift_pixels)
                if _profiling:
                    self._dr_profile_times['shift_panels'] += time.perf_counter() - t0

                    t0 = time.perf_counter()
                for ch, _ in self._channel_layout:
                    spec_key = self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=ch)
                    amp_key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=ch)
                    x0, _, x1, _ = self._data_regions[spec_key]
                    pw = x1 - x0
                    sx = pw - shift_pixels
                    self._dr_paint_spectrogram_strip(ch, spec_key, sx, shift_pixels, window_min, window_max)
                    self._dr_paint_amplitude_strip(ch, amp_key, sx, shift_pixels, window_min, window_max)
                if _profiling:
                    self._dr_profile_times['paint_strips'] += time.perf_counter() - t0

        # Apply axis overlay (layer 1 -> 2)
        if _profiling:
            t0 = time.perf_counter()
        self._dr_save_axis_underlay()
        if _profiling:
            self._dr_profile_times['save_axis'] += time.perf_counter() - t0

            t0 = time.perf_counter()
        self._dr_apply_all_axis_overlays()
        if _profiling:
            self._dr_profile_times['apply_axis'] += time.perf_counter() - t0

        # Apply overlays (layer 2 -> 3): oscilloscope, position lines, time text
        if _profiling:
            t0 = time.perf_counter()
        self._dr_save_overlay_regions(t, axes_xlim)
        if _profiling:
            self._dr_profile_times['save_overlays'] += time.perf_counter() - t0

        # Oscilloscope overlays (drawn before position lines so lines appear on top)
        if self._osc_enabled:
            if _profiling:
                t0 = time.perf_counter()
            for ch, _ in self._channel_layout:
                self._dr_osc_draw(ch, t)
            if _profiling:
                self._dr_profile_times['draw_oscilloscope'] += time.perf_counter() - t0

        if _profiling:
            t0 = time.perf_counter()
        self._dr_draw_position_lines(t, axes_xlim)
        if _profiling:
            self._dr_profile_times['draw_lines'] += time.perf_counter() - t0

        if self._dr_time_enabled and self._handles['time'] is not None:
            if _profiling:
                t0 = time.perf_counter()
            self._dr_draw_time_text(t)
            if _profiling:
                self._dr_profile_times['draw_time'] += time.perf_counter() - t0

        # Update state
        self._dr_prev_window_min = window_min

        if _profiling:
            self._dr_profile_times['total_render'] += time.perf_counter() - t0_total
            self._dr_profile_frame_count += 1
            if self._dr_profile_frame_count >= self._dr_profile_interval:
                self._dr_print_profile()

        # Buffer is already RGB -- return directly (contiguous for fast tobytes)
        return self._dr_frame_buffer

    def _set_dynamic_elements_visible(self, visible: bool):
        """Show/hide all dynamic per-frame elements."""
        for channel_id in self._handles['amplitude_peak_fills']:
            self._handles['amplitude_peak_fills'][channel_id].set_visible(visible)
        for channel_id in self._handles['amplitude_rms_fills']:
            self._handles['amplitude_rms_fills'][channel_id].set_visible(visible)
        for channel_id in self._handles['spectrogram_images']:
            self._handles['spectrogram_images'][channel_id].set_visible(visible)
        for line in self._handles['position_lines']:
            line.set_visible(visible)
        if self._handles['time'] is not None:
            self._handles['time'].set_visible(visible)

    def update_window_length(self, new_length):
        """Update the sliding window length dynamically (e.g., for zoom controls).
        Must be called after prepare_direct_render()."""
        self._window_length = new_length

        # Invalidate cached window lengths
        self.__amplitude_window_length = None
        self.__spectrogram_window_length = None

        # Update scroll dynamics
        self._dr_pixels_per_second = self._dr_panel_width / self._window_length
        self._dr_never_scrolls = self.es_audio.length <= self._window_length

        # Force full re-render on next frame
        self._dr_buffer_initialized = False
        self._dr_scroll_accumulator = 0.0

    # --- Shift-and-paint methods ---

    def _dr_compute_scroll(self, window_min) -> int:
        """Compute integer pixel shift from sub-pixel scroll accumulator.
        Returns shift_pixels (>= 0), or -1 to signal full re-render needed."""
        delta_seconds = window_min - self._dr_prev_window_min
        delta_pixels = delta_seconds * self._dr_pixels_per_second

        # If delta is abnormally large, force full re-render
        if delta_pixels >= self._dr_panel_width or delta_pixels < 0:
            self._dr_scroll_accumulator = 0.0
            return -1

        self._dr_scroll_accumulator += delta_pixels
        shift_int = round(self._dr_scroll_accumulator)
        self._dr_scroll_accumulator -= shift_int
        return max(0, shift_int)

    def _dr_shift_panels(self, shift_pixels):
        """Shift each data region left by shift_pixels within the frame buffer."""
        for key in self._dr_data_axes_keys:
            x0, y0, x1, y1 = self._data_regions[key]
            self._dr_frame_buffer[y0:y1, x0:x1 - shift_pixels] = \
                self._dr_frame_buffer[y0:y1, x0 + shift_pixels:x1]

    def _dr_render_full_panels(self, window_min, window_max):
        """Full-width render for first frame or fallback."""
        for ch, _ in self._channel_layout:
            spec_key = self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=ch)
            amp_key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=ch)
            x0, _, x1, _ = self._data_regions[spec_key]
            pw = x1 - x0
            self._dr_paint_spectrogram_strip(ch, spec_key, 0, pw, window_min, window_max)
            self._dr_paint_amplitude_strip(ch, amp_key, 0, pw, window_min, window_max)

    def _dr_paint_spectrogram_strip(self, channel_id, panel_key, strip_x_start, strip_width,
                                     window_min, window_max):
        """Render a spectrogram region (strip or full panel) into the frame buffer."""
        x0, y0, x1, y1 = self._data_regions[panel_key]
        panel_width = x1 - x0
        panel_height = y1 - y0
        invert = self._dr_invert[panel_key]
        window_length = window_max - window_min

        if strip_width <= 0 or panel_width <= 0 or panel_height <= 0 or window_length <= 0:
            return

        # Time range for the strip columns
        strip_time_start = window_min + (strip_x_start / panel_width) * window_length
        strip_time_end = window_min + ((strip_x_start + strip_width) / panel_width) * window_length

        # Map to spectrogram column indices
        spec_times = self._dr_spec_times
        col_start = max(0, np.searchsorted(spec_times, strip_time_start, side='left') - 1)
        col_end = min(len(spec_times), np.searchsorted(spec_times, strip_time_end, side='right') + 1)

        if col_end <= col_start:
            return

        # Slice raw dB spectrogram data
        spec_db = self.spectrogram.spectrogram_data[channel_id, :, col_start:col_end]

        # Flip for origin='lower' (unless inverted)
        if not invert:
            spec_db = spec_db[::-1]

        # Resize in data space BEFORE applying colormap -- interpolating dB values produces
        # clean color transitions, whereas interpolating in RGB creates false intermediate colors
        pil_data = Image.fromarray(spec_db.astype(np.float32), 'F')
        pil_data = pil_data.resize((strip_width, panel_height), Image.LANCZOS)
        resized_db = np.array(pil_data)

        # Apply colormap to the resized data
        rgba_float = self._dr_spec_cmaps[channel_id](self._dr_spec_norm(resized_db))
        spec_uint8 = (np.clip(rgba_float[:, :, :3], 0, 1) * 255).astype(np.uint8)

        # Write into frame buffer
        self._dr_frame_buffer[y0:y1, x0 + strip_x_start:x0 + strip_x_start + strip_width] = spec_uint8

    def _dr_paint_amplitude_strip(self, channel_id, panel_key, strip_x_start, strip_width,
                                   window_min, window_max):
        """Render an amplitude region (strip or full panel) into the frame buffer."""
        x0, y0, x1, y1 = self._data_regions[panel_key]
        panel_width = x1 - x0
        panel_height = y1 - y0
        invert = self._dr_invert[panel_key]
        window_length = window_max - window_min

        if strip_width <= 0 or panel_width <= 0 or panel_height <= 0 or window_length <= 0:
            return

        # Time range for strip columns
        strip_time_start = window_min + (strip_x_start / panel_width) * window_length
        strip_time_end = window_min + ((strip_x_start + strip_width) / panel_width) * window_length

        # Create strip buffer filled with background color
        strip = np.empty((panel_height, strip_width, 3), dtype=np.uint8)
        strip[:] = self._dr_amp_bg_rgb[channel_id]

        # Interpolate peak amplitude for each strip pixel column
        pixel_times = np.linspace(strip_time_start, strip_time_end, strip_width)
        pixel_amplitudes = np.interp(pixel_times, self._dr_peak_times,
                                      self._dr_peak_data[channel_id])

        # Convert to pixel heights
        pixel_heights = np.clip(
            pixel_amplitudes / self._dr_amp_y_max[channel_id] * panel_height, 0, panel_height).astype(np.int32)

        # Vectorized fill
        rows = np.arange(panel_height)[:, np.newaxis]
        if not invert:
            mask = rows >= (panel_height - pixel_heights)[np.newaxis, :]
        else:
            mask = rows < pixel_heights[np.newaxis, :]
        strip[mask] = self._dr_amp_peak_rgb[channel_id]

        # RMS overlay
        if self._dr_show_rms:
            pixel_rms = np.interp(pixel_times, self._dr_rms_times,
                                   self._dr_rms_data[channel_id])
            rms_heights = np.clip(
                pixel_rms / self._dr_amp_y_max[channel_id] * panel_height, 0, panel_height).astype(np.int32)
            if not invert:
                rms_mask = rows >= (panel_height - rms_heights)[np.newaxis, :]
            else:
                rms_mask = rows < rms_heights[np.newaxis, :]
            strip[rms_mask] = self._dr_amp_rms_rgb[channel_id]

        # Write into frame buffer
        self._dr_frame_buffer[y0:y1, x0 + strip_x_start:x0 + strip_x_start + strip_width] = strip

    def _dr_save_axis_underlay(self):
        """Save clean data pixels underneath axis overlay positions."""
        for key in self._dr_overlay_indices:
            ys, xs = self._dr_overlay_indices[key]
            self._dr_overlay_underlay[key] = self._dr_frame_buffer[ys, xs].copy()

    def _dr_restore_axis_underlay(self):
        """Restore clean data pixels at axis overlay positions."""
        for key in self._dr_overlay_underlay:
            ys, xs = self._dr_overlay_indices[key]
            self._dr_frame_buffer[ys, xs] = self._dr_overlay_underlay[key]

    def _dr_apply_all_axis_overlays(self):
        """Stamp axis overlay pixel values at pre-computed positions."""
        for key in self._dr_overlay_values:
            ys, xs = self._dr_overlay_indices[key]
            self._dr_frame_buffer[ys, xs] = self._dr_overlay_values[key]

    def _dr_save_overlay_regions(self, t, axes_xlim):
        """Save pixel regions under position lines and time text before drawing."""
        self._dr_saved_regions = []
        half_lw = self._position_line_width_px // 2
        xlim_min, xlim_max = axes_xlim
        xlim_range = xlim_max - xlim_min

        # Data panel position lines
        if xlim_range > 0:
            x_frac = (t - xlim_min) / xlim_range
            for key in self._dr_data_axes_keys:
                x0, y0, x1, y1 = self._data_regions[key]
                w = x1 - x0
                x_px = x0 + int(x_frac * w)
                x_start = max(x0, x_px - half_lw)
                x_end = min(x1, x_px + half_lw + 1)
                if x_start < x_end:
                    saved = self._dr_frame_buffer[y0:y1, x_start:x_end].copy()
                    self._dr_saved_regions.append((y0, y1, x_start, x_end, saved))

        # Oscilloscope box regions
        self._dr_osc_boxes = {}
        if self._osc_enabled:
            for ch, _ in self._channel_layout:
                box = self._dr_osc_compute_box(ch)
                if box is not None:
                    self._dr_osc_boxes[ch] = box
                    bx0, by0, bx1, by1 = box
                    saved = self._dr_frame_buffer[by0:by1, bx0:bx1].copy()
                    self._dr_saved_regions.append((by0, by1, bx0, bx1, saved))

        # Scrub panel position lines
        if self.es_audio.length > 0:
            scrub_x_frac = t / self.es_audio.length
            for key in self._scrub_regions:
                x0, y0, x1, y1 = self._scrub_regions[key]
                w = x1 - x0
                x_px = x0 + int(scrub_x_frac * w)
                x_start = max(x0, x_px - half_lw)
                x_end = min(x1, x_px + half_lw + 1)
                if x_start < x_end:
                    saved = self._dr_frame_buffer[y0:y1, x_start:x_end].copy()
                    self._dr_saved_regions.append((y0, y1, x_start, x_end, saved))

        # Time text region
        if self._dr_time_enabled and self._handles['time'] is not None:
            time_string = self._get_time_text()
            text_img = self._dr_get_time_text_image(time_string)
            th, tw = text_img.shape[:2]
            margin = max(2, self._dr_time_font_size_px // 8)
            tx = self._dr_fig_width - tw - margin
            ty = margin if self._dr_time_position_top else self._dr_fig_height - th - margin
            tx = max(0, tx)
            ty = max(0, ty)
            tx_end = min(self._dr_fig_width, tx + tw)
            ty_end = min(self._dr_fig_height, ty + th)
            if tx < tx_end and ty < ty_end:
                saved = self._dr_frame_buffer[ty:ty_end, tx:tx_end].copy()
                self._dr_saved_regions.append((ty, ty_end, tx, tx_end, saved))

    def _dr_restore_overlay_regions(self):
        """Restore pixel regions saved from previous frame's overlays."""
        for y0, y1, x_start, x_end, saved_pixels in self._dr_saved_regions:
            self._dr_frame_buffer[y0:y1, x_start:x_end] = saved_pixels
        self._dr_saved_regions = []

    def _dr_draw_position_lines(self, t, axes_xlim):
        """Draw position lines on data panels and scrub panels."""
        half_lw = self._position_line_width_px // 2
        xlim_min, xlim_max = axes_xlim
        xlim_range = xlim_max - xlim_min

        # Position in data subplots
        if xlim_range > 0:
            x_frac = (t - xlim_min) / xlim_range
            for key in self._dr_data_axes_keys:
                x0, y0, x1, y1 = self._data_regions[key]
                w = x1 - x0
                x_px = x0 + int(x_frac * w)
                x_start = max(x0, x_px - half_lw)
                x_end = min(x1, x_px + half_lw + 1)
                if x_start < x_end:
                    self._dr_frame_buffer[y0:y1, x_start:x_end] = self._position_line_color

        # Position in scrub subplots
        if self.es_audio.length > 0:
            scrub_x_frac = t / self.es_audio.length
            for key in self._scrub_regions:
                x0, y0, x1, y1 = self._scrub_regions[key]
                w = x1 - x0
                x_px = x0 + int(scrub_x_frac * w)
                x_start = max(x0, x_px - half_lw)
                x_end = min(x1, x_px + half_lw + 1)
                if x_start < x_end:
                    self._dr_frame_buffer[y0:y1, x_start:x_end] = self._position_line_color

    def _dr_draw_time_text(self, t):
        """Draw time text onto the frame buffer using cached rendered text."""
        time_string = self._get_time_text()
        text_img = self._dr_get_time_text_image(time_string)
        th, tw = text_img.shape[:2]
        margin = max(2, self._dr_time_font_size_px // 8)
        tx = self._dr_fig_width - tw - margin
        ty = margin if self._dr_time_position_top else self._dr_fig_height - th - margin

        tx = max(0, tx)
        ty = max(0, ty)
        tx_end = min(self._dr_fig_width, tx + tw)
        ty_end = min(self._dr_fig_height, ty + th)

        if tx >= tx_end or ty >= ty_end:
            return

        # Alpha composite the RGBA text image onto the RGB frame buffer
        text_region = text_img[:ty_end - ty, :tx_end - tx]
        alpha = text_region[:, :, 3:4].astype(np.float32) / 255.0
        bg = self._dr_frame_buffer[ty:ty_end, tx:tx_end].astype(np.float32)
        fg = text_region[:, :, :3].astype(np.float32)
        blended = fg * alpha + bg * (1.0 - alpha)
        self._dr_frame_buffer[ty:ty_end, tx:tx_end] = blended.astype(np.uint8)

    def _dr_get_time_text_image(self, text_string) -> np.ndarray:
        """Render time text to a cached RGBA numpy array."""
        if text_string not in self._dr_time_text_cache:
            # Measure text size
            dummy_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            draw = ImageDraw.Draw(dummy_img)
            bbox = draw.textbbox((0, 0), text_string, font=self._dr_time_font,
                                  stroke_width=self._dr_time_border_width)
            tw = bbox[2] - bbox[0] + 2 * self._dr_time_border_width
            th = bbox[3] - bbox[1] + 2 * self._dr_time_border_width

            text_img = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_img)
            draw.text(
                (-bbox[0] + self._dr_time_border_width,
                 -bbox[1] + self._dr_time_border_width),
                text_string, font=self._dr_time_font,
                fill=(*self._dr_time_color, 255),
                stroke_width=self._dr_time_border_width,
                stroke_fill=(*self._dr_time_border_color, 255))

            self._dr_time_text_cache[text_string] = np.array(text_img)

        return self._dr_time_text_cache[text_string]

    # --- VideoVisualization overridden subplot methods ---

    def _add_amplitude_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec,
                               invert: bool = False, scrub: bool = False):
        if self._handles['figure'] is None:
            return

        axis_type = AxisTypes.AMPLITUDE_SCRUB if scrub else AxisTypes.AMPLITUDE
        axes_style_cfg = self._get_amplitude_style_cfg(channel_id)

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=axis_type, channel=channel_id)] = ax
        self._format_amplitude_axes(ax=ax, channel_id=channel_id, invert=invert, hideaxis=scrub)

        ax.set_facecolor(axes_style_cfg['background-color'])

        # If rendering a video, only render the amplitude envelope here if making a scrub subplot
        # since otherwise it the contents will change with each frame
        if scrub:
            ax.set_xlim(self.peak_envelope.times[0], self.peak_envelope.times[len(self.peak_envelope.times) - 1])
            ax.fill(self.peak_envelope.times, self.peak_envelope.envelope_data[channel_id, :],
                    color=axes_style_cfg['base-color'])

            if es.cfg['visualization.style.amplitude.show-rms']:
                ax.fill(self.rms_envelope.times, self.rms_envelope.envelope_data[channel_id, :],
                        color=axes_style_cfg['rms-color'])

        self._handles['position_lines'].append(
            ax.axvline(x=0, lw=1, color=es.cfg['visualization.style.video.position-line-color']))

    def _add_figure_subplots(self, gridspec: matplotlib.gridspec.GridSpec) -> int:
        i_subplot = super()._add_figure_subplots(gridspec=gridspec)

        # Additional amplitude subplots if rendering a video to show envelopes for full file for scrubbing purposes
        for channel_id, invert in self._scrub_channel_layout:
            self._add_amplitude_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot],
                                        invert=invert, scrub=True)
            i_subplot += 1

        return i_subplot

    def _add_spectrogram_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec, invert: bool = False):
        if self._handles['figure'] is None:
            return

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)] = ax
        self._format_spectrogram_axes(ax=ax, invert=invert)

        # If rendering a video, don't bother rendering the spectrogram since it will change with each frame
        self._handles['position_lines'].append(
            ax.axvline(x=0, lw=1, color=es.cfg['visualization.style.video.position-line-color']))

    def _frame_to_time(self, frame):
        return frame / self.fps

    def _get_gridspec_params(self):
        gridspec_params = super()._get_gridspec_params()

        amp_ratio = es.cfg[f'visualization.style.subplot-height-ratios.amplitude.{self._layout_ratio_key}']
        for ch_id, invert in self._scrub_channel_layout:
            gridspec_params['height_ratios'].append(amp_ratio / 2)

        gridspec_params['nrows'] = len(gridspec_params['height_ratios'])

        return gridspec_params

    def _get_time_text(self) -> str:
        return es.utils.seconds_to_string(self._frame_to_time(self._frame)) + ' / ' \
            + es.utils.seconds_to_string(self.es_audio.length)

    def _get_window_range(self, t, total_length, window_length, round_bounds: bool = False):
        # Calculate half the window length
        half_window_length = window_length / 2

        # If rounding the bounds, floor the half width
        if round_bounds:
            half_window_length = math.floor(half_window_length)

        # Ensure the min is not less than 0 or greater than one full window length from the end of the data
        window_min = max(0, min(total_length - window_length, t - half_window_length))
        # Ensure the max doesn't run past the end of the data
        window_max = max(min(total_length, window_length), min(total_length, t + half_window_length))

        return window_min, window_max

    def _initialize_handles(self):
        super()._initialize_handles()

        self._handles['position_lines'] = []
        self._handles['video_frame'] = []
        self._handles['amplitude_peak_fills'] = {}
        self._handles['amplitude_rms_fills'] = {}
        self._handles['spectrogram_images'] = {}

    def _set_animation(self):
        if self._handles['figure'] is None:
            return

        self._animation = matplotlib.animation.FuncAnimation(fig=self._handles['figure'], func=self.make_frame,
                                                             frames=self.frames, repeat=False, cache_frame_data=False,
                                                             interval=1)

    def _time_to_frame(self, time):
        return math.floor(time * self.fps)

    def _update_time_text(self):
        if self._handles['time'] is None:
            return

        if self._time_enabled():
            self._handles['time'].set_text(self._get_time_text())
        else:
            self._handles['time'].set_text('')

    @classmethod
    def _time_enabled(cls, mode: VisualizationMode = VisualizationMode.EXPORT) -> bool:
        return es.cfg['visualization.video.export.time.enabled']

    @classmethod
    def _time_position(cls) -> str:
        return es.cfg['visualization.video.export.time.position']

    @classmethod
    def _title_enabled(cls, mode: VisualizationMode = VisualizationMode.EXPORT) -> bool:
        return es.cfg['visualization.video.export.title.enabled']
