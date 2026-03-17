"""Oscilloscope waveform overlay mixin for video visualization.

OscilloscopeMixin provides per-channel oscilloscope overlays that display
trigger-stabilized raw audio waveforms. The mixin pattern is used because
the oscilloscope methods share extensive instance state with VideoVisualization
(frame buffer, data regions, amplitude colors, spectrogram times, etc.).
"""

import math

import estimpy as es
import matplotlib.colors
import numpy as np
import scipy.fft
from PIL import Image, ImageDraw, ImageFont

from estimpy.visualization.base import AxisTypes


class OscilloscopeMixin:
    """Mixin providing oscilloscope overlay rendering for VideoVisualization.

    Expects the host class to provide:
    - self._es_audio: Audio object
    - self._dr_frame_buffer: numpy RGB frame buffer
    - self._data_regions: dict of panel pixel regions
    - self._dr_amp_bg_rgb, self._dr_amp_peak_rgb: per-channel color arrays
    - self._channel_layout: list of (channel_id, invert)
    - self._get_axis_handle_id(): axis key helper
    - self._text_border_width: text border width for font rendering
    """

    def _dr_osc_init(self, fig):
        """Initialize oscilloscope state. Called from prepare_direct_render()."""
        self._osc_enabled = es.cfg['visualization.video.export.oscilloscope.enabled']
        self._osc_manual_duration = None  # None = auto mode, float seconds = manual override
        self._dr_osc_boxes = {}
        self._dr_osc_prev_waveform = {}  # per-channel template for correlation trigger
        self._dr_osc_mode = {}  # per-channel: 'tone' or 'pulse'

        # Initialize hold to force tone mode until enough audio has played for
        # the centered analysis window to have a full backward half
        pulse_count_threshold = es.cfg['analysis.oscilloscope.pulse-detection.count-threshold']
        pulse_window_length_init = es.cfg['analysis.oscilloscope.pulse-detection.window-length'] / 1000.0
        initial_hold = pulse_count_threshold * pulse_window_length_init
        self._dr_osc_mode_hold_until = {ch: initial_hold for ch, _ in self._channel_layout}
        self._dr_osc_last_time = {}  # per-channel: last seen time for detecting seeks

        # Oscilloscope label font setup — derive the pixel size using the same
        # scaling that resize_figure applied to matplotlib text elements. Since
        # resize_figure changes both the figure size and DPI, we recover the
        # effective scale factor from any already-scaled text element rather than
        # computing it from canvas dimensions alone.
        fig_width_px, fig_height_px = fig.canvas.get_width_height()
        display_height = es.cfg['visualization.image.display.height']
        display_dpi = 100  # _DISPLAY_DPI in base.py — the canonical starting DPI
        fig_dpi = fig.get_dpi()
        # resize_figure computes: height_scale_factor = (target_h / current_h) * (current_dpi / target_dpi)
        # The net effect on font pixel size is: config_pt * height_scale_factor * (target_dpi / 72)
        # Which simplifies to: config_pt * (fig_height_px / display_height) * (display_dpi / 72)
        # because fig_height_px = target_h and the DPI factors cancel.
        osc_font_size_pt = es.cfg['visualization.style.oscilloscope.font-size']
        self._dr_osc_font_size_px = max(1, int(round(
            osc_font_size_pt * (fig_height_px / display_height) * (display_dpi / 72))))
        font_file = es.cfg['visualization.style.font.text.file']
        face_index = es.cfg['visualization.style.font.text.face-index']
        self._dr_osc_font = ImageFont.truetype(font_file, self._dr_osc_font_size_px, index=face_index)
        axes_color_rgb = matplotlib.colors.to_rgb(es.cfg['visualization.style.axes.color'])
        self._dr_osc_label_color = tuple(int(c * 255) for c in axes_color_rgb)
        border_color_rgb = matplotlib.colors.to_rgb(es.cfg['visualization.style.font.text.border-color'])
        self._dr_osc_label_border_color = tuple(int(c * 255) for c in border_color_rgb)
        self._dr_osc_label_border_width = max(1, int(round(self._text_border_width * self._pt_to_px)))
        self._dr_osc_border_width_px = max(1, int(round(
            es.cfg['visualization.style.oscilloscope.border-width'] * self._pt_to_px)))
        self._dr_osc_line_width_px = max(1, int(round(
            es.cfg['visualization.style.oscilloscope.line-width'] * self._pt_to_px)))

        # Label image cache — duration labels are stable (keyed by ms value),
        # frequency and RMS labels change per frame and are keyed by their string
        self._dr_osc_label_cache = {}
        duration_tone = es.cfg['analysis.oscilloscope.window-length']
        duration_pulse = es.cfg['analysis.oscilloscope.pulse-detection.window-length']
        for dur_ms in (duration_tone, duration_pulse):
            label = f'{int(dur_ms)} ms' if dur_ms == int(dur_ms) else f'{dur_ms} ms'
            self._dr_osc_label_cache[label] = self._dr_osc_render_label(label)

    def _dr_osc_compute_box(self, channel_id):
        """Compute pixel bounding box (x0, y0, x1, y1) for oscilloscope overlay on a channel.
        Uses the steady-state position (panel center) so the box doesn't grow during the
        initial scroll-in period."""
        amp_key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=channel_id)
        spec_key = self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)
        amp_region = self._data_regions[amp_key]
        spec_region = self._data_regions[spec_key]

        # Combined panel region
        panel_x0 = amp_region[0]
        panel_x1 = amp_region[2]
        panel_y0 = min(amp_region[1], spec_region[1])
        panel_y1 = max(amp_region[3], spec_region[3])
        panel_width = panel_x1 - panel_x0
        panel_height = panel_y1 - panel_y0

        # Use steady-state position line location (center of panel)
        steady_state_x_frac = 0.5
        pos_x = panel_x0 + int(steady_state_x_frac * panel_width)
        available_width = pos_x - panel_x0

        # Box dimensions from config
        width_ratio = es.cfg['visualization.style.oscilloscope.width-ratio']
        height_ratio = es.cfg['visualization.style.oscilloscope.height-ratio']

        box_width = int(width_ratio * panel_width)
        box_width = min(box_width, available_width)
        if box_width < 40:
            return None

        box_height = int(height_ratio * panel_height)
        if box_height < 10:
            return None

        # Center horizontally between left edge and steady-state position line
        center_x = panel_x0 + available_width // 2
        bx0 = max(panel_x0, center_x - box_width // 2)
        bx1 = min(pos_x, bx0 + box_width)

        # Center vertically in combined panel
        center_y = panel_y0 + panel_height // 2
        by0 = max(panel_y0, center_y - box_height // 2)
        by1 = min(panel_y1, by0 + box_height)

        return (bx0, by0, bx1, by1)

    def _dr_osc_detect_mode(self, channel_id, current_time):
        """Detect whether the signal is tonal or pulsed using coefficient of variation
        analysis across a centered window around the current playback position.
        The centered window ensures mode switches happen at/near the actual transition
        -- the backward half must show the new signal character before detection fires."""
        pulse_window_length = es.cfg['analysis.oscilloscope.pulse-detection.window-length'] / 1000.0
        pulse_cv_threshold = es.cfg['analysis.oscilloscope.pulse-detection.cv-threshold']
        pulse_count_threshold = es.cfg['analysis.oscilloscope.pulse-detection.count-threshold']
        sample_rate = self._es_audio.sample_rate
        total_samples = self._es_audio.data.shape[1]
        sub_window_seconds = 0.002  # 2ms sub-windows for CV analysis

        current_mode = self._dr_osc_mode.get(channel_id, 'tone')

        # Detect backward time jump (seek or stop/restart) and reset mode state
        last_time = self._dr_osc_last_time.get(channel_id, 0)
        self._dr_osc_last_time[channel_id] = current_time
        if current_time < last_time - 0.1:
            self._dr_osc_mode[channel_id] = 'tone'
            self._dr_osc_mode_hold_until[channel_id] = current_time + pulse_count_threshold * pulse_window_length
            self._dr_osc_prev_waveform.pop(channel_id, None)
            current_mode = 'tone'

        # Don't switch modes until hold period expires
        hold_until = self._dr_osc_mode_hold_until.get(channel_id, 0)
        if current_time < hold_until:
            return current_mode

        # Slightly backward-weighted analysis window: 55% behind, 45% ahead.
        analysis_length = 2 * pulse_count_threshold * pulse_window_length
        analysis_samples = max(10, int(analysis_length * sample_rate))
        backward_samples = int(analysis_samples * 0.55)
        forward_samples = analysis_samples - backward_samples
        center_sample = int(current_time * sample_rate)
        start_sample = max(0, center_sample - backward_samples)
        end_sample = min(total_samples, center_sample + forward_samples)

        if end_sample - start_sample < 10:
            return current_mode

        buffer = self._es_audio.data[channel_id, start_sample:end_sample].astype(np.float32)

        # Compute RMS in short sub-windows (2ms)
        sub_window_samples = max(1, int(sub_window_seconds * sample_rate))
        n_windows = len(buffer) // sub_window_samples
        if n_windows < 3:
            return current_mode

        trimmed = buffer[:n_windows * sub_window_samples].reshape(n_windows, sub_window_samples)
        sub_rms = np.sqrt(np.mean(trimmed ** 2, axis=1))

        # Divide the analysis window into chunks of pulse window-length and compute
        # CV for each. Require at least count-threshold chunks to exceed
        # cv-threshold, confirming sustained pulsing rather than an isolated transient.
        pulse_sub_window_samples = max(1, int(pulse_window_length * sample_rate))
        pulse_sub_rms_windows = pulse_sub_window_samples // sub_window_samples
        if pulse_sub_rms_windows < 3:
            return current_mode

        pulse_count = 0
        for offset in range(0, n_windows - pulse_sub_rms_windows + 1, pulse_sub_rms_windows):
            chunk = sub_rms[offset:offset + pulse_sub_rms_windows]
            chunk_mean = np.mean(chunk)
            if chunk_mean > 1e-10:
                cv = np.std(chunk) / chunk_mean
                if cv >= pulse_cv_threshold:
                    # Verify sharp energy transitions exist (not smooth AM envelope).
                    # Pulse edges create large frame-to-frame RMS jumps; smooth AM
                    # tones change gradually.
                    chunk_diff = np.abs(np.diff(chunk))
                    chunk_peak = np.max(chunk)
                    max_edge = np.max(chunk_diff) / chunk_peak if chunk_peak > 1e-10 else 0
                    if max_edge >= 0.15:
                        pulse_count += 1

        detected_mode = 'pulse' if pulse_count >= pulse_count_threshold else 'tone'

        if detected_mode != current_mode:
            self._dr_osc_mode[channel_id] = detected_mode
            self._dr_osc_prev_waveform.pop(channel_id, None)
            # Hold the new mode for the full analysis window length so the detector
            # sees entirely new data before reconsidering — prevents oscillation when
            # signals are borderline (e.g., AM-modulated tonal content).
            self._dr_osc_mode_hold_until[channel_id] = current_time + analysis_length
            return detected_mode

        return current_mode

    def _dr_osc_find_trigger_zero_crossing(self, waveform):
        """Fallback trigger: rising zero-crossing with hysteresis."""
        peak = np.max(np.abs(waveform))
        silence_threshold = es.cfg['analysis.oscilloscope.silence-threshold']
        if peak < silence_threshold:
            return 0

        hysteresis = es.cfg['analysis.oscilloscope.trigger-hysteresis']
        arm_level = -hysteresis * peak

        armed = False
        for i in range(len(waveform) - 1):
            if not armed:
                if waveform[i] <= arm_level:
                    armed = True
            else:
                if waveform[i] <= 0 and waveform[i + 1] > 0:
                    return i
        return 0

    def _dr_osc_find_trigger_correlation(self, search_buffer, template):
        """Find the best trigger offset by cross-correlating the search buffer with
        the previous frame's waveform template. Returns (offset, quality) where
        quality is the normalized correlation score (0-1)."""
        # Normalize both signals for correlation
        template_norm = template - np.mean(template)
        template_energy = np.dot(template_norm, template_norm)
        if template_energy < 1e-10:
            return 0, 0.0

        search_len = len(search_buffer) - len(template) + 1
        if search_len <= 0:
            return 0, 0.0

        # Sliding normalized cross-correlation
        # Use 'valid' mode: output length = len(search_buffer) - len(template) + 1
        corr = np.correlate(search_buffer - np.mean(search_buffer), template_norm, mode='valid')

        # Normalize by the energy of each windowed segment of the search buffer
        # Use cumulative sum trick for efficient windowed energy computation
        search_sq = (search_buffer - np.mean(search_buffer)) ** 2
        cumsum = np.concatenate(([0.0], np.cumsum(search_sq)))
        window_energy = cumsum[len(template):] - cumsum[:search_len]

        # Avoid division by zero
        valid = window_energy > 1e-10
        normalized_corr = np.zeros_like(corr)
        normalized_corr[valid] = corr[valid] / np.sqrt(window_energy[valid] * template_energy)

        best_offset = int(np.argmax(normalized_corr))
        best_score = float(normalized_corr[best_offset])

        return best_offset, best_score

    def _dr_osc_extract_waveform(self, channel_id, current_time):
        """Extract a trigger-stabilized waveform segment for display.

        The right edge of the displayed waveform corresponds to current_time,
        ensuring all channels share the same time reference. The trigger search
        shifts the start point backward by at most one cycle to find a clean
        alignment, but the end point stays fixed at current_time.

        Duration is determined by manual override or the current auto mode
        (tone or pulse). Uses cross-correlation with the previous frame's
        waveform for smooth tracking, falling back to zero-crossing trigger
        when no template exists or correlation quality is too low."""
        if self._osc_manual_duration is not None:
            duration = self._osc_manual_duration
        elif es.cfg['analysis.oscilloscope.pulse-detection.enabled']:
            mode = self._dr_osc_detect_mode(channel_id, current_time)
            if mode == 'pulse':
                duration = es.cfg['analysis.oscilloscope.pulse-detection.window-length'] / 1000.0
            else:
                duration = es.cfg['analysis.oscilloscope.window-length'] / 1000.0
        else:
            duration = es.cfg['analysis.oscilloscope.window-length'] / 1000.0
        silence_threshold = es.cfg['analysis.oscilloscope.silence-threshold']

        sample_rate = self._es_audio.sample_rate
        display_samples = max(10, int(duration * sample_rate))

        # The right edge of the display = current_time. The buffer extends
        # backward by display_samples + trigger_margin. The trigger can shift
        # the start point within the margin to find a clean zero-crossing or
        # correlation match, but the displayed window always ends at current_time.
        # No forward look-ahead — we never display audio that hasn't played yet.
        end_sample = int(current_time * sample_rate)
        trigger_margin = max(int(0.005 * sample_rate), display_samples)
        buf_start = max(0, end_sample - display_samples - trigger_margin)
        buf_end = min(self._es_audio.data.shape[1], end_sample)

        if buf_end - buf_start < display_samples:
            self._dr_osc_prev_waveform.pop(channel_id, None)
            return np.zeros(display_samples, dtype=np.float32), duration

        buffer = self._es_audio.data[channel_id, buf_start:buf_end].astype(np.float32)

        # RMS check
        rms = np.sqrt(np.mean(buffer ** 2))
        if rms < silence_threshold:
            self._dr_osc_prev_waveform.pop(channel_id, None)
            return np.zeros(display_samples, dtype=np.float32), duration

        # The trigger search finds the best start offset within the margin.
        # The search range is [0, trigger_margin] in buffer coordinates.
        # For any trigger_idx found, the displayed window is
        # buffer[trigger_idx : trigger_idx + display_samples].
        search_range = len(buffer) - display_samples
        if search_range <= 0:
            result = buffer[-display_samples:]
            self._dr_osc_prev_waveform[channel_id] = result.copy()
            return result, duration

        trigger_idx = 0
        prev_template = self._dr_osc_prev_waveform.get(channel_id)

        if prev_template is not None and len(prev_template) == display_samples:
            # Correlation-based trigger using previous frame's waveform as template.
            # For long display windows (pulse mode), decimate both signals to keep
            # the O(n^2) cross-correlation fast. Target ~1000 samples per template.
            dec_factor = max(1, display_samples // 1000)
            if dec_factor > 1:
                dec_buffer = buffer[::dec_factor]
                dec_template = prev_template[::dec_factor]
                dec_search_range = search_range // dec_factor
                dec_display = len(dec_template)
                corr_offset, corr_quality = self._dr_osc_find_trigger_correlation(
                    dec_buffer[:dec_search_range + dec_display], dec_template)
                corr_offset *= dec_factor  # Scale back to full resolution
            else:
                corr_offset, corr_quality = self._dr_osc_find_trigger_correlation(
                    buffer[:search_range + display_samples], prev_template)

            if corr_quality > 0.3:
                trigger_idx = corr_offset
            else:
                # Signal changed too much -- fall back to zero-crossing
                trigger_idx = self._dr_osc_find_trigger_zero_crossing(buffer[:search_range])
        else:
            # No previous template or length changed -- use zero-crossing
            trigger_idx = self._dr_osc_find_trigger_zero_crossing(buffer[:search_range])

        # Clamp to valid range
        trigger_idx = max(0, min(trigger_idx, search_range))

        result = buffer[trigger_idx:trigger_idx + display_samples]
        self._dr_osc_prev_waveform[channel_id] = result.copy()
        return result, duration

    def _dr_osc_render_label(self, text):
        """Render a duration label string to a cached RGBA numpy array."""
        dummy_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=self._dr_osc_font,
                              stroke_width=self._dr_osc_label_border_width)
        tw = bbox[2] - bbox[0] + 2 * self._dr_osc_label_border_width
        th = bbox[3] - bbox[1] + 2 * self._dr_osc_label_border_width

        text_img = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_img)
        draw.text(
            (-bbox[0] + self._dr_osc_label_border_width,
             -bbox[1] + self._dr_osc_label_border_width),
            text, font=self._dr_osc_font,
            fill=(*self._dr_osc_label_color, 255),
            stroke_width=self._dr_osc_label_border_width,
            stroke_fill=(*self._dr_osc_label_border_color, 255))

        return np.array(text_img)

    def _dr_osc_get_label(self, text):
        """Get a cached rendered label image, rendering on demand if needed."""
        label_img = self._dr_osc_label_cache.get(text)
        if label_img is None:
            label_img = self._dr_osc_render_label(text)
            self._dr_osc_label_cache[text] = label_img
        return label_img

    def _dr_osc_composite_label(self, label_img, bx0, by0, lx, ly):
        """Alpha-composite a rendered label image onto the frame buffer."""
        lh, lw = label_img.shape[:2]
        alpha = label_img[:, :, 3:4].astype(np.float32) / 255.0
        bg_region = self._dr_frame_buffer[by0 + ly:by0 + ly + lh, bx0 + lx:bx0 + lx + lw].astype(np.float32)
        fg = label_img[:, :, :3].astype(np.float32)
        composited = fg * alpha + bg_region * (1.0 - alpha)
        self._dr_frame_buffer[by0 + ly:by0 + ly + lh, bx0 + lx:bx0 + lx + lw] = composited.astype(np.uint8)

    @staticmethod
    def _dr_osc_format_duration(duration_s):
        """Format a duration in seconds as a human-readable string."""
        duration_ms = duration_s * 1000.0
        if duration_ms >= 1000:
            secs = duration_ms / 1000.0
            return f'{int(secs)} s' if secs == int(secs) else f'{secs:.1f} s'
        if duration_ms == int(duration_ms):
            return f'{int(duration_ms)} ms'
        return f'{duration_ms:.1f} ms'

    @staticmethod
    def _dr_osc_estimate_peak_freq(waveform, sample_rate):
        """Estimate the peak frequency of a waveform using zero-padded FFT."""
        n = len(waveform)
        if n < 4:
            return 0.0
        rms = np.sqrt(np.mean(waveform ** 2))
        if rms < 1e-6:
            return 0.0
        # Zero-pad to at least 4x for sub-bin frequency resolution
        nfft = max(n * 4, 1024)
        windowed = waveform * np.hanning(n)
        spectrum = np.abs(scipy.fft.rfft(windowed, n=nfft))
        # Skip DC bin
        peak_bin = np.argmax(spectrum[1:]) + 1
        return peak_bin * sample_rate / nfft

    @staticmethod
    def _dr_osc_format_freq(freq_hz):
        """Format a frequency in Hz as a human-readable string."""
        if freq_hz >= 1000:
            khz = freq_hz / 1000.0
            return f'{khz:.1f} kHz' if khz != int(khz) else f'{int(khz)} kHz'
        return f'{int(round(freq_hz))} Hz'

    @staticmethod
    def _dr_osc_format_level(waveform):
        """Compute peak and RMS levels of a waveform and format as dBFS."""
        peak = np.max(np.abs(waveform))
        rms = np.sqrt(np.mean(waveform ** 2))
        if peak < 1e-10:
            return 'Pk -\u221e \u00b7 RMS -\u221e dB'
        peak_db = 20 * math.log10(peak)
        rms_db = 20 * math.log10(max(rms, 1e-10))
        return f'Pk {peak_db:.1f} \u00b7 RMS {rms_db:.1f} dB'

    def _dr_osc_draw(self, channel_id, current_time):
        """Draw the oscilloscope overlay for one channel."""
        if channel_id not in self._dr_osc_boxes:
            return

        box = self._dr_osc_boxes[channel_id]
        bx0, by0, bx1, by1 = box
        box_width = bx1 - bx0
        box_height = by1 - by0

        # Extract triggered waveform and current duration
        waveform, duration = self._dr_osc_extract_waveform(channel_id, current_time)

        # Alpha-blend background
        opacity = es.cfg['visualization.style.oscilloscope.opacity']
        bg_rgb = self._dr_amp_bg_rgb[channel_id].astype(np.float32)
        region = self._dr_frame_buffer[by0:by1, bx0:bx1].astype(np.float32)
        blended = region * (1.0 - opacity) + bg_rgb * opacity
        self._dr_frame_buffer[by0:by1, bx0:bx1] = blended.astype(np.uint8)

        # Draw border using channel base color at 5x the background opacity
        border_width = self._dr_osc_border_width_px
        if border_width > 0:
            border_opacity = min(1.0, opacity * 5.0)
            border_rgb = self._dr_amp_peak_rgb[channel_id].astype(np.float32)

            # Top edge
            bw_top = min(border_width, box_height)
            top_region = self._dr_frame_buffer[by0:by0 + bw_top, bx0:bx1].astype(np.float32)
            self._dr_frame_buffer[by0:by0 + bw_top, bx0:bx1] = (
                top_region * (1.0 - border_opacity) + border_rgb * border_opacity).astype(np.uint8)

            # Bottom edge
            bw_bot = min(border_width, box_height)
            bot_region = self._dr_frame_buffer[by1 - bw_bot:by1, bx0:bx1].astype(np.float32)
            self._dr_frame_buffer[by1 - bw_bot:by1, bx0:bx1] = (
                bot_region * (1.0 - border_opacity) + border_rgb * border_opacity).astype(np.uint8)

            # Left edge (excluding corners already drawn)
            bw_left = min(border_width, box_width)
            inner_y0 = by0 + bw_top
            inner_y1 = by1 - bw_bot
            if inner_y1 > inner_y0:
                left_region = self._dr_frame_buffer[inner_y0:inner_y1, bx0:bx0 + bw_left].astype(np.float32)
                self._dr_frame_buffer[inner_y0:inner_y1, bx0:bx0 + bw_left] = (
                    left_region * (1.0 - border_opacity) + border_rgb * border_opacity).astype(np.uint8)

            # Right edge (excluding corners already drawn)
            bw_right = min(border_width, box_width)
            if inner_y1 > inner_y0:
                right_region = self._dr_frame_buffer[inner_y0:inner_y1, bx1 - bw_right:bx1].astype(np.float32)
                self._dr_frame_buffer[inner_y0:inner_y1, bx1 - bw_right:bx1] = (
                    right_region * (1.0 - border_opacity) + border_rgb * border_opacity).astype(np.uint8)

        # Map waveform to pixel coordinates
        line_color = self._dr_amp_peak_rgb[channel_id]
        line_width = self._dr_osc_line_width_px
        half_lw = max(0, line_width // 2)
        padding_frac = 0.05

        if len(waveform) == 0:
            return

        num_samples = len(waveform)
        usable_height = box_height * (1 - 2 * padding_frac)
        center_y = box_height / 2

        if num_samples <= box_width:
            # Upsampling: more pixels than samples -- plot each sample at its
            # sub-pixel position and connect with vertical lines for full fidelity
            y_samples = (center_y - waveform * usable_height / 2).astype(np.int32)
            y_samples = np.clip(y_samples, 0, box_height - 1)

            for i in range(num_samples - 1):
                # X pixel range this segment spans
                x0_f = i * (box_width - 1) / (num_samples - 1)
                x1_f = (i + 1) * (box_width - 1) / (num_samples - 1)
                x0_px = int(x0_f)
                x1_px = int(x1_f)

                ya = y_samples[i]
                yb = y_samples[i + 1]

                # Draw vertical line at each pixel column, interpolating y
                for x in range(x0_px, x1_px + 1):
                    if x1_px > x0_px:
                        frac = (x - x0_f) / (x1_f - x0_f)
                    else:
                        frac = 0.0
                    y_interp = int(ya + frac * (yb - ya))
                    y_interp = max(0, min(box_height - 1, y_interp))

                    # For the connecting segment, also fill to previous column's y
                    if x == x0_px:
                        y_top = max(0, min(ya, y_interp) - half_lw)
                        y_bot = min(box_height - 1, max(ya, y_interp) + half_lw)
                    else:
                        # Get previous column's interpolated y
                        prev_frac = (x - 1 - x0_f) / (x1_f - x0_f) if x1_px > x0_px else 0.0
                        y_prev = int(ya + prev_frac * (yb - ya))
                        y_prev = max(0, min(box_height - 1, y_prev))
                        y_top = max(0, min(y_prev, y_interp) - half_lw)
                        y_bot = min(box_height - 1, max(y_prev, y_interp) + half_lw)

                    self._dr_frame_buffer[by0 + y_top:by0 + y_bot + 1, bx0 + x] = line_color
        else:
            # Downsampling: more samples than pixels -- use min/max per column
            # to preserve peaks and high-frequency detail
            for x in range(box_width):
                # Map this pixel column to a range of samples
                s0 = int(x * num_samples / box_width)
                s1 = int((x + 1) * num_samples / box_width)
                s1 = max(s0 + 1, min(s1, num_samples))
                chunk = waveform[s0:s1]

                y_min_val = float(np.min(chunk))
                y_max_val = float(np.max(chunk))

                y_top_px = int(center_y - y_max_val * usable_height / 2)
                y_bot_px = int(center_y - y_min_val * usable_height / 2)

                y_top_px = max(0, min(box_height - 1, y_top_px - half_lw))
                y_bot_px = max(0, min(box_height - 1, y_bot_px + half_lw))

                self._dr_frame_buffer[by0 + y_top_px:by0 + y_bot_px + 1, bx0 + x] = line_color

        # Draw labels: duration (left), peak frequency (center), peak+RMS level (right)
        margin = max(2, self._dr_osc_font_size_px // 4)
        inner_left = border_width + margin
        inner_right = box_width - border_width - margin

        # Prepare all label images and positions
        dur_text = self._dr_osc_format_duration(duration)
        dur_img = self._dr_osc_get_label(dur_text)
        dur_h, dur_w = dur_img.shape[:2]
        dur_x = inner_left
        dur_y = box_height - dur_h - border_width - margin

        level_text = self._dr_osc_format_level(waveform)
        level_img = self._dr_osc_get_label(level_text)
        level_h, level_w = level_img.shape[:2]
        level_x = inner_right - level_w
        level_y = box_height - level_h - border_width - margin

        # Duration — bottom-left (always drawn if it fits)
        if dur_x + dur_w <= inner_right and dur_y >= 0:
            self._dr_osc_composite_label(dur_img, bx0, by0, dur_x, dur_y)

        # Peak + RMS level — bottom-right (only if it doesn't overlap duration)
        level_drawn = False
        if level_x >= dur_x + dur_w + margin and level_y >= 0:
            self._dr_osc_composite_label(level_img, bx0, by0, level_x, level_y)
            level_drawn = True

        # Peak frequency — bottom-center (only if it fits between the other two)
        peak_freq = self._dr_osc_estimate_peak_freq(waveform, self._es_audio.sample_rate)
        if peak_freq > 0:
            freq_text = self._dr_osc_format_freq(peak_freq)
            freq_img = self._dr_osc_get_label(freq_text)
            freq_h, freq_w = freq_img.shape[:2]
            freq_x = (box_width - freq_w) // 2
            freq_y = box_height - freq_h - border_width - margin
            right_bound = level_x - margin if level_drawn else inner_right
            if (freq_x >= dur_x + dur_w + margin
                    and freq_x + freq_w <= right_bound
                    and freq_y >= 0):
                self._dr_osc_composite_label(freq_img, bx0, by0, freq_x, freq_y)
