import math

import numpy as np
import pytest

import estimpy as es
from estimpy.analysis import (
    Envelope,
    EnvelopeModes,
    Spectrogram,
    SpectrogramScaling,
    calculate_optimal_nfft,
    estimate_frequency_max_coarse,
    peak_envelope,
    rms_envelope,
)
from tests.conftest import SAMPLE_RATE, N_SAMPLES


class TestEnvelope:
    def test_peak_envelope_shape(self, synthetic_stereo_audio):
        env = peak_envelope(synthetic_stereo_audio)
        assert env.envelope_data.shape[0] == 2  # 2 channels
        assert env.envelope_data.shape[1] > 0

    def test_peak_envelope_range(self, synthetic_stereo_audio):
        env = peak_envelope(synthetic_stereo_audio)
        assert env.envelope_data.max() <= 1.0
        assert env.envelope_data.min() >= 0.0  # peak of abs values

    def test_rms_less_than_peak(self, synthetic_stereo_audio):
        p = peak_envelope(synthetic_stereo_audio)
        r = rms_envelope(synthetic_stereo_audio)
        # RMS should generally be <= peak for the same signal
        assert r.envelope_data.max() <= p.envelope_data.max() + 1e-6

    def test_envelope_times_monotonic(self, synthetic_stereo_audio):
        env = peak_envelope(synthetic_stereo_audio)
        diffs = np.diff(env.times)
        assert np.all(diffs > 0)

    def test_envelope_mode_property(self, synthetic_stereo_audio):
        env = peak_envelope(synthetic_stereo_audio)
        assert env.mode == EnvelopeModes.PEAK
        env_r = rms_envelope(synthetic_stereo_audio)
        assert env_r.mode == EnvelopeModes.RMS

    def test_envelope_with_padding(self, synthetic_stereo_audio):
        padding = 5
        env = peak_envelope(synthetic_stereo_audio, padding=padding)
        env_no_pad = peak_envelope(synthetic_stereo_audio, padding=0)
        # Padded version should have 2*padding more time steps
        assert env.envelope_data.shape[1] == env_no_pad.envelope_data.shape[1] + 2 * padding

    def test_pad_envelope_data_1d(self):
        data = np.array([1.0, 2.0, 3.0])
        padding = np.array([0.0, 0.0])
        result = Envelope.pad_envelope_data(data, padding)
        assert result.shape == (7,)
        assert result[0] == 0.0
        assert result[-1] == 0.0

    def test_pad_envelope_data_2d(self):
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        padding = np.array([0.0])
        result = Envelope.pad_envelope_data(data, padding)
        assert result.shape == (2, 4)


class TestSpectrogram:
    def test_spectrogram_shape_3d(self, synthetic_stereo_audio):
        spec = Spectrogram(synthetic_stereo_audio)
        assert len(spec.spectrogram_data.shape) == 3
        assert spec.spectrogram_data.shape[0] == 2  # channels

    def test_spectrogram_frequency_range(self, synthetic_stereo_audio):
        spec = Spectrogram(synthetic_stereo_audio)
        assert spec.frequencies[0] >= 0
        assert spec.frequencies[-1] <= spec.frequency_max

    def test_spectrogram_times_monotonic(self, synthetic_stereo_audio):
        spec = Spectrogram(synthetic_stereo_audio)
        diffs = np.diff(spec.times)
        assert np.all(diffs > 0)

    def test_spectrogram_detects_440hz(self, synthetic_stereo_audio):
        # Use standard spectrogram (no reassignment) for predictable peak detection
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            window_size=2048, window_overlap=1024, nfft=4096,
            frequency_min=0, frequency_max=2000,
            scaling=SpectrogramScaling.LINEAR, reassign=False
        )
        # Channel 0 (left) has 440Hz — find the peak frequency
        ch0_power = data[0].mean(axis=1)  # average across time
        peak_freq_idx = np.argmax(ch0_power)
        peak_freq = freqs[peak_freq_idx]
        assert abs(peak_freq - 440) < 20  # within 20Hz

    def test_spectrogram_stereo_independent(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            window_size=2048, window_overlap=1024, nfft=4096,
            frequency_min=0, frequency_max=2000,
            scaling=SpectrogramScaling.LINEAR, reassign=False
        )
        # Peak frequency should differ between channels (440 vs 880)
        ch0_peak = np.argmax(data[0].mean(axis=1))
        ch1_peak = np.argmax(data[1].mean(axis=1))
        assert ch0_peak != ch1_peak

    def test_spectrogram_db_scaling(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            window_size=2048, window_overlap=1024, nfft=4096,
            frequency_min=0, frequency_max=2000,
            scaling=SpectrogramScaling.DB, reassign=False
        )
        # dB-scaled values should be mostly negative (magnitude < 1 before log)
        assert data.max() < 0 or data.min() < 0

    def test_generate_spectrogram_mono(self, synthetic_mono_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_mono_audio.data, SAMPLE_RATE,
            window_size=2048, window_overlap=1024, nfft=4096,
            frequency_min=0, frequency_max=2000,
            scaling=SpectrogramScaling.LINEAR, reassign=False
        )
        assert data.shape[0] == 1  # one channel


class TestCentersToEdges:
    def test_basic(self):
        centers = np.array([1.0, 2.0, 3.0])
        edges = Spectrogram._centers_to_edges(centers)
        assert len(edges) == 4
        assert edges[0] == 0.5
        assert edges[-1] == 3.5

    def test_single_center(self):
        centers = np.array([5.0])
        edges = Spectrogram._centers_to_edges(centers)
        assert len(edges) == 2


class TestOptimalNfft:
    def test_returns_power_of_2(self):
        nfft = calculate_optimal_nfft(44100, 5000, 500, 2048)
        assert nfft > 0
        assert (nfft & (nfft - 1)) == 0  # power of 2

    def test_scales_with_panel_height(self):
        small = calculate_optimal_nfft(44100, 5000, 200, 2048)
        large = calculate_optimal_nfft(44100, 5000, 800, 2048)
        assert large >= small

    def test_minimum_is_window_size(self):
        nfft = calculate_optimal_nfft(44100, 20000, 10, 2048)
        assert nfft >= 2048

    def test_zero_frequency_returns_window_size(self):
        assert calculate_optimal_nfft(44100, 0, 500, 2048) == 2048

    def test_zero_panel_height_returns_window_size(self):
        assert calculate_optimal_nfft(44100, 5000, 0, 2048) == 2048


class TestEstimateFrequencyMaxCoarse:
    def test_detects_reasonable_frequency(self, synthetic_stereo_audio):
        freq_max = estimate_frequency_max_coarse(
            synthetic_stereo_audio.data, SAMPLE_RATE
        )
        # Should detect that energy is below ~1000Hz (440 and 880)
        assert freq_max >= 880
        assert freq_max <= SAMPLE_RATE / 2

    def test_pretty_mode_rounds(self, synthetic_stereo_audio):
        freq_max = estimate_frequency_max_coarse(
            synthetic_stereo_audio.data, SAMPLE_RATE, pretty_mode=True
        )
        # Pretty mode rounds to nearest 250/500/1000
        assert freq_max % 250 == 0 or freq_max % 500 == 0 or freq_max % 1000 == 0


class TestReassignedSpectrogram:
    """Tests for the reassigned spectrogram algorithm (a headline v2.0.0 feature)."""

    SPEC_PARAMS = dict(
        window_size=2048, window_overlap=1536, nfft=4096,
        frequency_min=0, frequency_max=2000,
    )

    def test_output_shape_3d(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )
        assert len(data.shape) == 3
        assert data.shape[0] == 2

    def test_non_negative_magnitude(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )
        assert np.all(data >= 0)

    def test_detects_440hz_channel_0(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )
        ch0_power = data[0].mean(axis=1)
        peak_freq = freqs[np.argmax(ch0_power)]
        assert abs(peak_freq - 440) < 30

    def test_detects_880hz_channel_1(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )
        ch1_power = data[1].mean(axis=1)
        peak_freq = freqs[np.argmax(ch1_power)]
        assert abs(peak_freq - 880) < 30

    def test_tighter_frequency_localization(self, synthetic_stereo_audio):
        """Reassigned spectrogram should concentrate energy more tightly around the true frequency."""
        std_freqs, _, std_data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=False,
            **self.SPEC_PARAMS
        )
        rea_freqs, _, rea_data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )

        # Measure energy concentration around 440Hz in channel 0
        def energy_ratio(freqs, data, center, bandwidth):
            mask = np.abs(freqs - center) <= bandwidth
            total = data[0].sum()
            if total == 0:
                return 0
            return data[0][mask].sum() / total

        std_ratio = energy_ratio(std_freqs, std_data, 440, 50)
        rea_ratio = energy_ratio(rea_freqs, rea_data, 440, 50)

        # Reassigned should have same or higher concentration
        assert rea_ratio >= std_ratio * 0.9  # allow small tolerance

    def test_smoothing_effect(self, synthetic_stereo_audio):
        """No smoothing should produce sparser output than smoothed."""
        es.cfg['analysis.spectrogram.reassign-smoothing'] = 0.0
        _, _, data_no_smooth = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )

        es.cfg['analysis.spectrogram.reassign-smoothing'] = 1.0
        _, _, data_smooth = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.LINEAR, reassign=True,
            **self.SPEC_PARAMS
        )

        # Unsmoothed has more near-zero bins (sparser)
        floor = 1e-9
        sparse_no_smooth = np.sum(data_no_smooth < floor) / data_no_smooth.size
        sparse_smooth = np.sum(data_smooth < floor) / data_smooth.size
        assert sparse_no_smooth >= sparse_smooth

    def test_db_scaling_has_negative_values(self, synthetic_stereo_audio):
        freqs, times, data = Spectrogram.generate_spectrogram_data(
            synthetic_stereo_audio.data, SAMPLE_RATE,
            scaling=SpectrogramScaling.DB, reassign=True,
            **self.SPEC_PARAMS
        )
        assert data.min() < 0
