import numpy as np
import pytest

from estimpy.audio import Audio, compute_ramp_gain, resample_audio_data
from conftest import TEST_MP3, SAMPLE_RATE, DURATION, N_SAMPLES


class TestAudioFromNumpy:
    def test_channels_stereo(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.channels == 2

    def test_channels_mono(self, synthetic_mono_audio):
        assert synthetic_mono_audio.channels == 1

    def test_sample_rate(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.sample_rate == SAMPLE_RATE

    def test_sample_count(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.sample_count == N_SAMPLES

    def test_length(self, synthetic_stereo_audio):
        assert abs(synthetic_stereo_audio.length - DURATION) < 1e-6

    def test_data_dtype_float32(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data.dtype == np.float32

    def test_data_normalized_range(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data.min() >= -1.0
        assert synthetic_stereo_audio.data.max() <= 1.0

    def test_data_shape(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data.shape == (2, N_SAMPLES)

    def test_data_c_contiguous(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data.flags['C_CONTIGUOUS']

    def test_bit_depth(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.bit_depth == 16


class TestAudioDataRaw:
    def test_raw_dtype_16bit(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data_raw.dtype == np.int16

    def test_raw_shape_matches_data(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.data_raw.shape == synthetic_stereo_audio.data.shape

    def test_raw_roundtrip_close(self, synthetic_stereo_audio):
        # Reconstructed raw should be close to original (within 1 LSB)
        t = np.linspace(0, DURATION, N_SAMPLES, endpoint=False)
        original_left = (np.sin(2 * np.pi * 440 * t) * 0.8 * 32767).astype(np.int16)
        np.testing.assert_allclose(
            synthetic_stereo_audio.data_raw[0], original_left, atol=1
        )


class TestAudioFromFile:
    def test_load_mp3(self):
        audio = Audio(file=TEST_MP3)
        assert audio.channels == 2
        assert audio.sample_rate == SAMPLE_RATE
        assert audio.length > 0
        assert audio.format == 'mp3'

    def test_file_property(self):
        audio = Audio(file=TEST_MP3)
        assert audio.file == TEST_MP3


class TestTriphase:
    def test_triphase_creates_3_channels(self, synthetic_stereo_audio):
        tri = synthetic_stereo_audio.with_triphase()
        assert tri.channels == 3

    def test_triphase_third_channel_negated_sum(self, synthetic_stereo_audio):
        tri = synthetic_stereo_audio.with_triphase()
        expected = -(synthetic_stereo_audio.data[0] + synthetic_stereo_audio.data[1])
        np.testing.assert_allclose(tri.data[2], expected, atol=1e-6)

    def test_triphase_preserves_original_channels(self, synthetic_stereo_audio):
        tri = synthetic_stereo_audio.with_triphase()
        np.testing.assert_array_equal(tri.data[0], synthetic_stereo_audio.data[0])
        np.testing.assert_array_equal(tri.data[1], synthetic_stereo_audio.data[1])

    def test_triphase_mono_raises(self, synthetic_mono_audio):
        with pytest.raises(ValueError, match='stereo'):
            synthetic_mono_audio.with_triphase()


class TestStereoStimProtection:
    def test_ss_preserves_channels(self, synthetic_stereo_audio):
        ss =synthetic_stereo_audio.with_stereo_stim()
        assert ss.channels == synthetic_stereo_audio.channels

    def test_ss_preserves_sample_count(self, synthetic_stereo_audio):
        ss =synthetic_stereo_audio.with_stereo_stim()
        assert ss.sample_count == synthetic_stereo_audio.sample_count

    def test_ss_preserves_sample_rate(self, synthetic_stereo_audio):
        ss =synthetic_stereo_audio.with_stereo_stim()
        assert ss.sample_rate == synthetic_stereo_audio.sample_rate

    def test_ss_output_dtype_float32(self, synthetic_stereo_audio):
        ss =synthetic_stereo_audio.with_stereo_stim()
        assert ss.data.dtype == np.float32

    def test_ss_attenuates_dc(self, synthetic_stereo_audio):
        """Stereo stim high-pass filter should remove DC offset."""
        # Add DC offset to audio
        dc_audio = Audio(
            audio_data=np.full((2, N_SAMPLES), 16000, dtype=np.int16),
            sample_rate=SAMPLE_RATE, bit_depth=16)
        ss =dc_audio.with_stereo_stim()
        # DC should be nearly eliminated
        assert abs(np.mean(ss.data[0])) < 0.01

    def test_ss_passes_midrange(self, synthetic_stereo_audio):
        """Stereo stim should pass 440 Hz signal with minimal attenuation."""
        ss =synthetic_stereo_audio.with_stereo_stim()
        original_rms = np.sqrt(np.mean(synthetic_stereo_audio.data[0] ** 2))
        filtered_rms = np.sqrt(np.mean(ss.data[0] ** 2))
        # 440 Hz is well within passband — should retain >90% of energy
        assert filtered_rms / original_rms > 0.9

    def test_ss_creates_temp_wav(self, synthetic_stereo_audio):
        ss =synthetic_stereo_audio.with_stereo_stim()
        assert ss.file is not None
        assert ss.file.endswith('.wav')

    def test_ss_mono_works(self, synthetic_mono_audio):
        ss =synthetic_mono_audio.with_stereo_stim()
        assert ss.channels == 1


class TestComputeRampGain:
    def test_zero_level_returns_one(self):
        assert compute_ramp_gain(0.5, 0.0, 1.0, 0, 0) == 1.0

    def test_at_end_returns_one(self):
        assert compute_ramp_gain(1.0, 0.0, 1.0, 50, 0) == 1.0

    def test_past_end_returns_one(self):
        assert compute_ramp_gain(2.0, 0.0, 1.0, 50, 0) == 1.0

    def test_at_start_returns_start_gain(self):
        assert compute_ramp_gain(0.0, 0.0, 1.0, 50, 0) == pytest.approx(0.5)

    def test_at_start_full_reduction(self):
        assert compute_ramp_gain(0.0, 0.0, 1.0, 100, 0) == pytest.approx(0.0)

    def test_before_start_returns_start_gain(self):
        assert compute_ramp_gain(0.0, 0.5, 1.0, 50, 0) == pytest.approx(0.5)

    def test_linear_midpoint(self):
        # Linear ramp (shape=0) from 50% level: start_gain=0.5, midpoint should be 0.75
        gain = compute_ramp_gain(0.5, 0.0, 1.0, 50, 0)
        assert gain == pytest.approx(0.75)

    def test_nonzero_shape_monotonic(self):
        # With any shape, gain should increase monotonically
        gains = [compute_ramp_gain(t, 0.0, 1.0, 80, 3) for t in np.linspace(0, 0.99, 20)]
        for i in range(1, len(gains)):
            assert gains[i] >= gains[i - 1]

    def test_negative_shape_monotonic(self):
        gains = [compute_ramp_gain(t, 0.0, 1.0, 80, -3) for t in np.linspace(0, 0.99, 20)]
        for i in range(1, len(gains)):
            assert gains[i] >= gains[i - 1]

    def test_level_clamped_at_100(self):
        # Level > 100 should be treated as 100
        assert compute_ramp_gain(0.0, 0.0, 1.0, 150, 0) == pytest.approx(0.0)


class TestRamp:
    def test_ramp_preserves_channels(self, synthetic_stereo_audio):
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.channels == synthetic_stereo_audio.channels

    def test_ramp_preserves_sample_count(self, synthetic_stereo_audio):
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.sample_count == synthetic_stereo_audio.sample_count

    def test_ramp_preserves_sample_rate(self, synthetic_stereo_audio):
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.sample_rate == synthetic_stereo_audio.sample_rate

    def test_ramp_output_dtype_float32(self, synthetic_stereo_audio):
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.data.dtype == np.float32

    def test_ramp_creates_temp_wav(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.ramp.level'] = 50
        es.cfg['audio.ramp.shape'] = 0
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.file is not None
        assert ramped.file.endswith('.wav')

    def test_ramp_zero_level_returns_self(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.ramp.level'] = 0
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped is synthetic_stereo_audio

    def test_ramp_reduces_start_amplitude(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.ramp.level'] = 50
        es.cfg['audio.ramp.shape'] = 0
        ramped = synthetic_stereo_audio.with_ramp()
        # First samples should be ~50% of original
        start_ratio = np.abs(ramped.data[0, :100]).mean() / np.abs(synthetic_stereo_audio.data[0, :100]).mean()
        assert start_ratio == pytest.approx(0.5, abs=0.05)

    def test_ramp_preserves_source_file(self, synthetic_stereo_audio):
        ramped = synthetic_stereo_audio.with_ramp()
        assert ramped.source_file == synthetic_stereo_audio.source_file


class TestFrequencyTransform:
    def test_no_transform_returns_self(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 1
        es.cfg['audio.frequency.shift'] = 0
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result is synthetic_stereo_audio

    def test_scale_preserves_channels(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.channels == synthetic_stereo_audio.channels

    def test_scale_preserves_sample_count(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.sample_count == synthetic_stereo_audio.sample_count

    def test_scale_preserves_sample_rate(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.sample_rate == synthetic_stereo_audio.sample_rate

    def test_scale_output_dtype_float32(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.data.dtype == np.float32

    def test_scale_creates_temp_wav(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.file is not None
        assert result.file.endswith('.wav')

    def test_scale_doubles_frequency(self, synthetic_stereo_audio):
        """Scaling by 2 should move the 440 Hz tone to ~880 Hz."""
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()

        # Compute FFT of left channel and find peak frequency
        fft = np.abs(np.fft.rfft(result.data[0]))
        freqs = np.fft.rfftfreq(result.sample_count, 1.0 / result.sample_rate)
        peak_freq = freqs[np.argmax(fft)]
        assert abs(peak_freq - 880) < 50  # Within 50 Hz tolerance

    def test_shift_moves_frequency(self, synthetic_stereo_audio):
        """Shifting by +250 Hz should move the 440 Hz tone to ~690 Hz."""
        import estimpy as es
        es.cfg['audio.frequency.shift'] = 250
        result = synthetic_stereo_audio.with_frequency_transform()

        fft = np.abs(np.fft.rfft(result.data[0]))
        freqs = np.fft.rfftfreq(result.sample_count, 1.0 / result.sample_rate)
        peak_freq = freqs[np.argmax(fft)]
        assert abs(peak_freq - 690) < 50

    def test_scale_and_shift_combined(self, synthetic_stereo_audio):
        """Scale 2x then shift +100 should move 440 Hz to ~980 Hz."""
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        es.cfg['audio.frequency.shift'] = 100
        result = synthetic_stereo_audio.with_frequency_transform()

        fft = np.abs(np.fft.rfft(result.data[0]))
        freqs = np.fft.rfftfreq(result.sample_count, 1.0 / result.sample_rate)
        peak_freq = freqs[np.argmax(fft)]
        assert abs(peak_freq - 980) < 50

    def test_negative_shift(self, synthetic_stereo_audio):
        """Shifting by -200 Hz should move the 440 Hz tone to ~240 Hz."""
        import estimpy as es
        es.cfg['audio.frequency.shift'] = -200
        result = synthetic_stereo_audio.with_frequency_transform()

        fft = np.abs(np.fft.rfft(result.data[0]))
        freqs = np.fft.rfftfreq(result.sample_count, 1.0 / result.sample_rate)
        peak_freq = freqs[np.argmax(fft)]
        assert abs(peak_freq - 240) < 50

    def test_downscale(self, synthetic_stereo_audio):
        """Scaling by 0.5 should move the 440 Hz tone to ~220 Hz."""
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 0.5
        result = synthetic_stereo_audio.with_frequency_transform()

        fft = np.abs(np.fft.rfft(result.data[0]))
        freqs = np.fft.rfftfreq(result.sample_count, 1.0 / result.sample_rate)
        peak_freq = freqs[np.argmax(fft)]
        assert abs(peak_freq - 220) < 50

    def test_mono_works(self, synthetic_mono_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_mono_audio.with_frequency_transform()
        assert result.channels == 1

    def test_preserves_source_file(self, synthetic_stereo_audio):
        import estimpy as es
        es.cfg['audio.frequency.scale'] = 2
        result = synthetic_stereo_audio.with_frequency_transform()
        assert result.source_file == synthetic_stereo_audio.source_file


class TestTimeToDataIndex:
    def test_zero(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.time_to_data_index(0.0) == 0

    def test_midpoint(self, synthetic_stereo_audio):
        idx = synthetic_stereo_audio.time_to_data_index(0.5)
        assert idx == int(0.5 * SAMPLE_RATE)

    def test_negative_returns_none(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.time_to_data_index(-0.1) is None

    def test_beyond_end_returns_none(self, synthetic_stereo_audio):
        assert synthetic_stereo_audio.time_to_data_index(2.0) is None


class TestResampleAudioData:
    def test_resample_halves_samples(self, synthetic_stereo_audio):
        new_rate = SAMPLE_RATE // 2
        resampled = resample_audio_data(
            synthetic_stereo_audio.data, SAMPLE_RATE, new_rate
        )
        expected_samples = N_SAMPLES // 2
        assert resampled.shape[0] == 2
        assert abs(resampled.shape[1] - expected_samples) <= 1

    def test_resample_preserves_channels(self, synthetic_stereo_audio):
        resampled = resample_audio_data(
            synthetic_stereo_audio.data, SAMPLE_RATE, 22050
        )
        assert resampled.shape[0] == synthetic_stereo_audio.channels
