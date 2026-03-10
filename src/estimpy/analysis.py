"""A module for analysis of audio data"""
import enum
import math

import estimpy as es
import numpy as np
import scipy


nfft_auto = False  # True when nfft was auto-calculated (user didn't set it explicitly)


class EnvelopeModes(enum.StrEnum):
    PEAK = 'peak'
    RMS = 'rms'


class Envelope:
    """Amplitude envelope of an audio signal, computed via sliding windows.

    :param es_audio: Audio source to analyze.
    :param mode: Envelope type — peak (max absolute value) or RMS per window.
    :param start: Start sample index.
    :param end: End sample index (defaults to full length).
    :param padding: Number of zero-value samples to prepend and append.
    :param window_size: Samples per window (defaults to ``analysis.window-size`` config).
    :param step_size: Hop size between windows (defaults to ``analysis.window-overlap`` config).
    """

    def __init__(self, es_audio: es.audio.Audio, mode: EnvelopeModes = EnvelopeModes.PEAK,
                 start: int = 0, end: int = None, padding: int = 0, window_size: int = None, step_size: int = None):
        self._mode = mode
        self._envelope_data = None
        self._times = None

        audio_data = es_audio.data

        if mode == EnvelopeModes.PEAK:
            audio_data = np.abs(audio_data)
        elif mode == EnvelopeModes.RMS:
            audio_data = np.square(audio_data)

        if end is None:
            end = es_audio.sample_count

        if window_size is None:
            window_size = es.cfg['analysis.window-size']

        if step_size is None:
            step_size = es.cfg['analysis.window-overlap']

        if start > es_audio.sample_count or end > es_audio.sample_count:
            raise Exception('Invalid start or end time for envelope.')

        # Vectorized envelope computation using stride tricks (avoids Python loop)
        channels = []
        for j in range(es_audio.channels):
            channel_data = audio_data[j, start:end]
            # Create overlapping windows view without copying data
            windows = np.lib.stride_tricks.sliding_window_view(channel_data, window_size)[::step_size]
            if mode == EnvelopeModes.PEAK:
                channels.append(np.max(windows, axis=1))
            elif mode == EnvelopeModes.RMS:
                channels.append(np.sqrt(np.mean(windows, axis=1)))
            else:
                channels.append(np.zeros(windows.shape[0]))
        self._envelope_data = np.array(channels)

        envelope_samples = self._envelope_data.size if es_audio.channels == 1 else self._envelope_data.shape[1]

        # Generate a range to count each sample, divide by the number of samples to run the range from 0 to 1, then
        # multiply by the length of the audio in seconds to scale from 0 to the length of the audio
        self._times = np.multiply(np.arange(0 - padding, envelope_samples + padding),
                                     es_audio.length / envelope_samples)

        if padding > 0:
            self._envelope_data = Envelope.pad_envelope_data(self._envelope_data, np.zeros(padding))

    @property
    def envelope_data(self) -> np.ndarray:
        return self._envelope_data

    @property
    def mode(self) -> EnvelopeModes:
        return self._mode

    @property
    def times(self) -> np.ndarray:
        return self._times

    @classmethod
    def pad_envelope_data(cls, envelope_data: np.ndarray, padding_data: np.ndarray = np.array([0])) -> np.ndarray:
        if len(envelope_data.shape) == 1:
            return np.concatenate((padding_data, envelope_data, padding_data))
        else:
            padding_data = np.tile(padding_data, (envelope_data.shape[0], 1))
            return np.concatenate((padding_data, envelope_data, padding_data), axis=1)


class SpectrogramFrequencyMaxMethods(enum.StrEnum):
    SPECTRAL_EDGE = 'spectral_edge'
    POWER_THRESHOLD = 'power_threshold'

class SpectrogramScaling(enum.StrEnum):
    LINEAR = 'linear'
    DB = 'db'

class Spectrogram:
    """Spectrogram of an audio signal with optional reassignment.

    Resamples audio if the max frequency is below Nyquist to reduce computation.
    Automatically detects max frequency from content if not configured.
    """

    def __init__(self, es_audio: es.audio.Audio, frequency_min: int = None, frequency_max: int = None):
        """
        :param es_audio: Audio source to analyze.
        :param frequency_min: Low frequency cutoff in Hz (defaults to config).
        :param frequency_max: High frequency cutoff in Hz (defaults to config, or auto-detected).
        """
        audio_data = es_audio.data
        sample_rate = es_audio.sample_rate

        self._frequencies = None
        self._times = None
        self._spectrogram_data = None
        self._frequency_min = frequency_min if frequency_min is not None else \
            es.cfg['analysis.spectrogram.frequency-min']
        self._frequency_max = frequency_max if frequency_max is not None else \
            es.cfg['analysis.spectrogram.frequency-max'] if es.cfg['analysis.spectrogram.frequency-max'] is not None else \
                self._get_frequency_max(audio_data=audio_data, sample_rate=sample_rate) \

        window_size = es.cfg['analysis.window-size']
        window_overlap = es.cfg['analysis.window-overlap']

        # If max frequency is less than our nyquist limit, resample the audio data
        # to limit the processing and memory requirements of the spectrogram
        if self.frequency_max < math.floor(sample_rate / 2):
            # Calculate new sample rate from max frequency using nyquist rule
            new_sample_rate = round(self.frequency_max * 2)
            resample_factor = sample_rate / new_sample_rate
            audio_data = es.audio.resample_audio_data(audio_data, sample_rate, new_sample_rate)

            sample_rate = new_sample_rate
            window_size = math.floor(window_size / resample_factor)
            window_overlap = math.floor(window_overlap / resample_factor)

        self._frequencies, self._times, self._spectrogram_data = self.generate_spectrogram_data(
            audio_data=audio_data,
            sample_rate=sample_rate,
            window_size=window_size,
            window_overlap=window_overlap,
            frequency_min=self.frequency_min,
            frequency_max=self.frequency_max
        )


    @property
    def frequencies(self) -> np.ndarray:
        """
        :return np.ndarray:
        """
        return self._frequencies

    @property
    def frequency_min(self) -> float:
        """
        :return float:
        """
        return self._frequency_min

    @property
    def frequency_max(self) -> float:
        """
        :return float:
        """
        return self._frequency_max

    @property
    def spectrogram_data(self) -> np.ndarray:
        """
        :return np.ndarray:
        """
        return self._spectrogram_data

    @property
    def times(self) -> np.ndarray:
        """
        :return np.ndarray:
        """
        return self._times

    @classmethod
    def generate_spectrogram_data(cls, audio_data: np.ndarray, sample_rate: int, window_function: str = None,
                                  window_size: int = None, window_overlap: int = None, nfft: int = None,
                                  frequency_min: float = None, frequency_max: float = None,
                                  scaling: SpectrogramScaling = SpectrogramScaling.DB,
                                  reassign: bool = None) -> \
                                      tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute a spectrogram (standard or reassigned) from raw audio data.

        :param audio_data: Array of shape (channels, samples).
        :param sample_rate: Sample rate in Hz.
        :param window_function: Window function name for scipy.signal (defaults to config).
        :param window_size: Samples per STFT window (defaults to config).
        :param window_overlap: Overlap in samples between consecutive windows (defaults to config).
        :param nfft: FFT size, scaled proportionally with window_size (defaults to config).
        :param frequency_min: Low frequency cutoff in Hz (defaults to config).
        :param frequency_max: High frequency cutoff in Hz (defaults to config or Nyquist).
        :param scaling: Output scaling — dB (log) or linear.
        :param reassign: Use reassigned spectrogram algorithm (defaults to config).
        :return: Tuple of (frequencies, times, spectrogram_data).
        """
        frequencies = None
        times = None
        spectrogram_data = None

        if window_function is None:
            window_function = es.cfg['analysis.spectrogram.window-function']

        if window_size is None:
            window_size = es.cfg['analysis.window-size']

        if window_overlap is None:
            window_overlap = es.cfg['analysis.window-overlap']

        if nfft is None:
            # Scale nfft proportionally with window_size. When audio is resampled
            # to a lower sample rate, window_size shrinks but the config nfft
            # stays at the original value — without scaling, this creates enormous
            # FFT arrays (e.g., 8192-point FFT on a 92-sample window).
            config_nfft = es.cfg['analysis.spectrogram.nfft']
            config_ws = es.cfg['analysis.window-size']
            nfft = max(round(config_nfft * window_size / config_ws), window_size)

        if frequency_min is None:
            frequency_min = es.cfg['analysis.spectrogram.frequency-min']

        if frequency_max is None:
            # If frequency max is not defined in config, use the nyquist limit (this function does not autoscale)
            frequency_max = es.cfg['analysis.spectrogram.frequency-max']\
                if es.cfg['analysis.spectrogram.frequency-max'] is not None else math.floor(sample_rate / 2)

        if reassign is None:
            reassign = es.cfg['analysis.spectrogram.reassign']

        nfft = max(nfft, window_size)

        # Build the window array for use with both standard and reassigned paths
        h = scipy.signal.get_window(window_function, window_size)

        if reassign:
            spectrogram_data = cls._generate_reassigned_spectrogram(
                audio_data=audio_data, sample_rate=sample_rate, window=h,
                window_size=window_size, window_overlap=window_overlap, nfft=nfft,
                frequency_min=frequency_min, frequency_max=frequency_max)
        else:
            # Standard spectrogram path
            for i in range(audio_data.shape[0]):
                frequencies, times, spectrogram_channel = scipy.signal.spectrogram(
                    audio_data[i, :].T,
                    fs=sample_rate,
                    window=h,
                    nperseg=window_size,
                    noverlap=window_overlap,
                    nfft=nfft,
                    scaling='spectrum',
                    mode='magnitude'
                )
                spectrogram_channel = spectrogram_channel.astype(np.float32).reshape(1, *spectrogram_channel.shape)

                if spectrogram_data is None:
                    spectrogram_data = spectrogram_channel
                else:
                    spectrogram_data = np.concatenate([spectrogram_data, spectrogram_channel], axis=0)

        # For the reassigned path, extract frequencies/times from the histogram grid
        # (already restricted to display range inside _generate_reassigned_spectrogram)
        if reassign:
            all_frequencies = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)
            freq_step = all_frequencies[1] - all_frequencies[0] if len(all_frequencies) > 1 else 1.0
            i_freq_min = max(0, math.floor(frequency_min / freq_step)) if frequency_min else 0
            if frequency_max is not None and frequency_max < all_frequencies[-1]:
                i_freq_max = min(len(all_frequencies) - 1, math.ceil(frequency_max / freq_step) + 1)
            else:
                i_freq_max = len(all_frequencies) - 1
            frequencies = all_frequencies[i_freq_min:i_freq_max + 1]

            hop = window_size - window_overlap
            n_samples = audio_data.shape[1] if len(audio_data.shape) > 1 else len(audio_data)
            times = np.arange(window_size // 2, n_samples - window_size // 2 + 1, hop) / sample_rate
        else:
            # Trim standard spectrogram to only include specified frequency range
            frequency_step = frequencies[1] - frequencies[0]
            i_frequency_min = math.floor(frequency_min / frequency_step)
            i_frequency_max = min(math.ceil(frequency_max / frequency_step) + 1, len(frequencies) - 1)

            frequencies = frequencies[i_frequency_min:i_frequency_max]

            if len(audio_data.shape) == 1:
                spectrogram_data = spectrogram_data[i_frequency_min:i_frequency_max, :]
            else:
                spectrogram_data = spectrogram_data[:, i_frequency_min:i_frequency_max, :]

        if scaling == SpectrogramScaling.DB:
            spectrogram_data = 20 * es.utils.log10_quiet(spectrogram_data)

        return frequencies, times, spectrogram_data

    @classmethod
    def _generate_reassigned_spectrogram(cls, audio_data: np.ndarray, sample_rate: int,
                                         window: np.ndarray, window_size: int,
                                         window_overlap: int, nfft: int,
                                         frequency_min: float = None,
                                         frequency_max: float = None) -> np.ndarray:
        """Compute a reassigned spectrogram using three windowed DFTs per channel.

        Uses np.fft.rfft directly (not scipy.signal.stft) to avoid window-sum
        normalization that breaks when sum(window) ≈ 0 for the derivative and
        time-ramped windows.

        Frames are processed in chunks to limit peak memory usage. Histogram bins
        are fixed, so partial histograms from each chunk are summed before the
        final smoothing step.

        Returns magnitude data on the same grid as a standard spectrogram (shape: channels x frequencies x times).
        """
        ref_power = np.float32(1e-6)

        # Derivative window (central difference)
        window_f32 = window.astype(np.float32)
        dh = np.gradient(window_f32)

        # Frequency and time axes for the output grid
        all_frequencies = np.fft.rfftfreq(nfft, d=1.0 / sample_rate).astype(np.float32)
        hop = window_size - window_overlap
        n_channels = audio_data.shape[0]

        # Compute standard time axis matching scipy.signal.spectrogram convention
        n_samples = audio_data.shape[1]
        times = (np.arange(window_size // 2, n_samples - window_size // 2 + 1, hop) / sample_rate).astype(np.float32)

        # Restrict histogram frequency bins to the display range.
        # The FFT still covers all frequencies, but the histogram and gaussian
        # filter only operate on the display range — points that reassign outside
        # are dropped, matching what the post-trim would have done anyway.
        freq_step = all_frequencies[1] - all_frequencies[0] if len(all_frequencies) > 1 else 1.0
        if frequency_min is not None and frequency_min > 0:
            i_freq_min = max(0, math.floor(frequency_min / freq_step))
        else:
            i_freq_min = 0
        if frequency_max is not None and frequency_max < all_frequencies[-1]:
            i_freq_max = min(len(all_frequencies) - 1, math.ceil(frequency_max / freq_step) + 1)
        else:
            i_freq_max = len(all_frequencies) - 1

        frequencies = all_frequencies[i_freq_min:i_freq_max + 1]
        freq_edges = cls._centers_to_edges(frequencies).astype(np.float64)
        time_edges = cls._centers_to_edges(times).astype(np.float64)

        # Normalize magnitude scaling factors
        win_sum = np.float32(np.sum(window_f32))
        sqrt2_f32 = np.float32(np.sqrt(2))
        half_nyquist = np.float32(sample_rate / 2)
        audio_length = np.float32(n_samples / sample_rate)
        n_freqs = nfft // 2 + 1

        # Chunk size: number of frames per chunk. Tuned to keep peak intermediate
        # memory per chunk under ~1-2 GB (n_freqs * chunk_size * 16 bytes for complex64 arrays).
        chunk_frames = max(1, min(10000, 500_000_000 // (n_freqs * 16)))

        spectrogram_data = None

        for i in range(n_channels):
            x = audio_data[i, :]

            # Extract overlapping frames using stride tricks (no boundary padding)
            all_frames = np.lib.stride_tricks.sliding_window_view(x, window_size)[::hop]
            n_frames = min(all_frames.shape[0], len(times))

            # Accumulate histograms across chunks
            n_freq_bins = len(frequencies)
            n_time_bins = len(times)
            hist_power = np.zeros((n_freq_bins, n_time_bins), dtype=np.float64)
            hist_count = np.zeros((n_freq_bins, n_time_bins), dtype=np.float64)

            for chunk_start in range(0, n_frames, chunk_frames):
                chunk_end = min(chunk_start + chunk_frames, n_frames)
                frames = all_frames[chunk_start:chunk_end]
                chunk_n = frames.shape[0]
                chunk_times = times[chunk_start:chunk_end]

                # Compute windowed DFTs directly — no normalization, so ratios are exact.
                # Use complex64 (single precision) to halve memory.
                S_h = np.fft.rfft(frames * window_f32, n=nfft, axis=1).astype(np.complex64).T
                S_dh = np.fft.rfft(frames * dh, n=nfft, axis=1).astype(np.complex64).T

                # Derive S_th from S_h using the frequency-domain relationship:
                # S_th[k] = j*nfft/(2π) * dS_h/dk - (window_size-1)/2 * S_h[k]
                # This eliminates one FFT (saves ~33% of FFT computation time).
                dS_h_dk = np.gradient(S_h, axis=0)
                S_th = np.complex64(1j * nfft / (2 * np.pi)) * dS_h_dk - np.float32((window_size - 1) / 2.0) * S_h
                del dS_h_dk

                # Use raw magnitude for mask and ratios (normalization cancels in ratios)
                raw_magnitude = np.abs(S_h)
                mask = raw_magnitude > ref_power

                # Normalize magnitude to match scipy.signal.spectrogram(mode='magnitude', scaling='spectrum')
                # which divides by sum(window) and doubles the one-sided spectrum
                magnitude = raw_magnitude / win_sum
                magnitude[1:-1, :] *= sqrt2_f32
                del raw_magnitude

                # Initialize reassigned coordinates at bin centers (use all FFT frequencies,
                # not the display-restricted ones — the histogram will handle the filtering)
                bin_freqs = np.broadcast_to(all_frequencies[:, np.newaxis], S_h.shape).copy()
                frame_times_chunk = np.broadcast_to(chunk_times[np.newaxis, :], S_h.shape).copy()

                # Compute reassigned coordinates where signal is above threshold
                ratio_dh = np.zeros_like(S_h)
                ratio_th = np.zeros_like(S_h)
                ratio_dh[mask] = S_dh[mask] / S_h[mask]
                ratio_th[mask] = S_th[mask] / S_h[mask]
                del S_h, S_dh, S_th

                reassigned_freqs = bin_freqs.copy()
                reassigned_times = frame_times_chunk.copy()
                del bin_freqs, frame_times_chunk
                reassigned_freqs[mask] -= np.imag(ratio_dh[mask]) * np.float32(sample_rate / (2 * np.pi))
                reassigned_times[mask] += np.real(ratio_th[mask]) / np.float32(sample_rate)
                del ratio_dh, ratio_th, mask

                # Clip to valid ranges
                np.clip(reassigned_freqs, 0, half_nyquist, out=reassigned_freqs)
                np.clip(reassigned_times, 0, audio_length, out=reassigned_times)

                # Scatter power onto the output grid and accumulate
                power = magnitude ** 2
                del magnitude
                chunk_hist_power, _, _ = np.histogram2d(
                    reassigned_freqs.ravel().astype(np.float64),
                    reassigned_times.ravel().astype(np.float64),
                    bins=[freq_edges, time_edges],
                    weights=power.ravel().astype(np.float64))
                chunk_hist_count, _, _ = np.histogram2d(
                    reassigned_freqs.ravel().astype(np.float64),
                    reassigned_times.ravel().astype(np.float64),
                    bins=[freq_edges, time_edges])
                del reassigned_freqs, reassigned_times, power

                hist_power += chunk_hist_power
                hist_count += chunk_hist_count
                del chunk_hist_power, chunk_hist_count

            # Nadaraya-Watson kernel smoothing: smooth both power and count with
            # the same Gaussian, then divide. This fills gaps between sparse
            # reassigned points while preserving per-source magnitude (no dilution).
            # Frequency sigma scales with zero-padding ratio so smoothing width
            # is relative to the true frequency resolution regardless of nfft.
            smoothing = es.cfg['analysis.spectrogram.reassign-smoothing']

            if smoothing > 0:
                zp_ratio = nfft / window_size
                sigma_freq = smoothing * zp_ratio / 2
                sigma_time = smoothing * 1.0
                smooth_power = scipy.ndimage.gaussian_filter(hist_power, sigma=(sigma_freq, sigma_time))
                smooth_count = scipy.ndimage.gaussian_filter(hist_count, sigma=(sigma_freq, sigma_time))

                avg_power = np.zeros_like(smooth_power)
                valid = smooth_count > 1e-6
                avg_power[valid] = smooth_power[valid] / smooth_count[valid]
            else:
                # No smoothing — raw per-bin average
                avg_power = np.zeros_like(hist_power)
                nonzero = hist_count > 0
                avg_power[nonzero] = hist_power[nonzero] / hist_count[nonzero]

            del hist_power, hist_count

            # Convert to float32 magnitude; set floor for near-zero bins to avoid
            # -inf after dB conversion (which corrupts LANCZOS resize)
            channel_data = np.sqrt(np.maximum(avg_power, 0)).astype(np.float32)
            channel_data[channel_data < 1e-10] = 1e-10
            channel_data = channel_data.reshape(1, *channel_data.shape)

            if spectrogram_data is None:
                spectrogram_data = channel_data
            else:
                spectrogram_data = np.concatenate([spectrogram_data, channel_data], axis=0)

        return spectrogram_data

    @staticmethod
    def _centers_to_edges(centers: np.ndarray) -> np.ndarray:
        """Convert bin center values to bin edges for np.histogram2d."""
        if len(centers) < 2:
            half = 0.5 if len(centers) == 0 else abs(centers[0]) * 0.5 or 0.5
            return np.array([centers[0] - half, centers[0] + half]) if len(centers) == 1 else np.array([0.0, 1.0])
        midpoints = (centers[:-1] + centers[1:]) / 2
        first_edge = centers[0] - (centers[1] - centers[0]) / 2
        last_edge = centers[-1] + (centers[-1] - centers[-2]) / 2
        return np.concatenate(([first_edge], midpoints, [last_edge]))

    @classmethod
    def _get_frequency_max(cls, audio_data: np.ndarray, sample_rate: int,
                           method: SpectrogramFrequencyMaxMethods = None,
                           padding_factor: float = None, pretty_mode: bool = True):
        if method is None:
            method = SpectrogramFrequencyMaxMethods(es.cfg['analysis.spectrogram.frequency-max-method'])

        if padding_factor is None:
            padding_factor = es.cfg['analysis.spectrogram.frequency-max-padding-factor']

        # Subsample the audio to limit computation: take evenly spaced segments
        # that add up to a bounded total (~5000 spectrogram frames worth of audio).
        # This produces a representative frequency analysis without processing the
        # entire file, which is critical for long files (10+ minutes).
        window_size = es.cfg['analysis.window-size']
        window_overlap = es.cfg['analysis.window-overlap']
        hop = window_size - window_overlap
        max_frames = 5000
        max_samples = max_frames * hop + window_size
        n_samples = audio_data.shape[1]

        if n_samples > max_samples * 1.5:
            # Take evenly spaced segments across the file
            n_segments = 10
            segment_samples = max_samples // n_segments
            # Ensure segment is at least one window
            segment_samples = max(segment_samples, window_size * 2)
            spacing = n_samples // n_segments
            segments = []
            for s in range(n_segments):
                start = s * spacing
                end = min(start + segment_samples, n_samples)
                segments.append(audio_data[:, start:end])
            sampled_audio = np.concatenate(segments, axis=1)
        else:
            sampled_audio = audio_data

        frequencies, times, spectrogram_data = cls.generate_spectrogram_data(sampled_audio, sample_rate,
                                                                             scaling=SpectrogramScaling.LINEAR,
                                                                             reassign=False)
        if len(spectrogram_data.shape) > 2:
            # Reshape spectrogram data to append all channels onto first
            # (since we want to determine the max frequency across all channels)
            spectrogram_data = spectrogram_data.transpose(1, 0, 2).reshape(spectrogram_data.shape[1], -1)

        frequency_max_index = frequencies.size - 1

        if method == SpectrogramFrequencyMaxMethods.SPECTRAL_EDGE:
            # Spectral edge frequency method
            # Calculate the cumulative sum of frequency magnitude at all time bins
            spectral_cumsum = np.cumsum(spectrogram_data, axis=0)

            # Remove times with no signal
            zero_times = np.where(spectral_cumsum[frequency_max_index, :] == 0)
            spectral_cumsum = np.delete(spectral_cumsum, zero_times, axis=1)

            # Remove times in the bottom 10% of signal magnitude
            # Get the list of time indices sorted by total frequency magnitude at that time
            sorted_times = np.argsort(spectral_cumsum[frequency_max_index, :])
            spectral_cumsum = np.delete(spectral_cumsum, sorted_times[range(math.floor(0.1 * spectral_cumsum.shape[1]))], axis=1)

            # Vectorized spectral edge computation across all time bins
            totals = spectral_cumsum[frequency_max_index, :]
            spec_edge80_indices = np.argmax(spectral_cumsum >= 0.8 * totals[np.newaxis, :], axis=0)
            spec_edge95_indices = np.argmax(spectral_cumsum >= 0.95 * totals[np.newaxis, :], axis=0)

            # Identify the frequency index of either the 95th percentile of the 80% spectral edge frequency
            # or the 50th percentile of the 95% spectral edge frequency
            frequency_max_index = max(
                math.floor(np.percentile(spec_edge80_indices, 95)),
                math.floor(np.percentile(spec_edge95_indices, 50)))
        elif method == SpectrogramFrequencyMaxMethods.POWER_THRESHOLD:
            # Power threshold method
            # Convert to decibels. Might have zero values which could lead to divide by zero errors when taking log
            spectrogram_data = np.multiply(es.utils.log10_quiet(spectrogram_data), 20)
            # Set the power threshold to 20% of the total dynamic range
            power_threshold = 0.2 * -es.cfg['visualization.style.spectrogram.dynamic-range']
            # Find the highest frequency whose 99.9 percentile power across all time bins is at least the power threshold
            frequency_max_index = len(frequencies) - np.argmax(
               np.flipud(np.percentile(spectrogram_data, 99.9, axis=1)) > power_threshold) - 1

        frequency_max = frequencies[frequency_max_index]

        # Add optional padding (for visual display)
        frequency_max *= padding_factor

        if pretty_mode:
            # Round the frequency to a pretty value
            if frequency_max < 1000:
                nearest_frequency = 250
            elif frequency_max < 2000:
                nearest_frequency = 500
            else:
                nearest_frequency = 1000

            frequency_max = nearest_frequency * math.ceil(frequency_max / nearest_frequency)

        # Don't allow the frequency_max to exceed the nyquist limit
        frequency_max = min(frequency_max, math.floor(sample_rate / 2))

        return frequency_max


def estimate_frequency_max_coarse(audio_data: np.ndarray, sample_rate: int,
                                  padding_factor: float = None,
                                  pretty_mode: bool = True) -> float:
    """Quick frequency estimation using a handful of FFTs.

    Samples ~20 evenly-spaced segments and computes periodograms with a
    moderate FFT size (1024). Much faster than a full spectrogram analysis.
    Used to determine optimal nfft before computing the full spectrogram.
    """
    if padding_factor is None:
        padding_factor = es.cfg['analysis.spectrogram.frequency-max-padding-factor']

    n_channels = audio_data.shape[0]
    n_samples = audio_data.shape[1]

    coarse_window_size = min(2048, n_samples)
    coarse_nfft = max(coarse_window_size, 1024)

    n_segments = min(20, max(1, n_samples // coarse_window_size))

    if n_segments <= 1:
        spacing = 0
    else:
        spacing = max(1, (n_samples - coarse_window_size) // (n_segments - 1))

    h = scipy.signal.get_window('hann', coarse_window_size).astype(np.float32)
    n_freqs = coarse_nfft // 2 + 1
    power_sum = np.zeros(n_freqs, dtype=np.float64)

    for i in range(n_segments):
        start = min(i * spacing, n_samples - coarse_window_size)
        for ch in range(n_channels):
            segment = audio_data[ch, start:start + coarse_window_size]
            spectrum = np.abs(np.fft.rfft(segment * h, n=coarse_nfft))
            power_sum += spectrum.astype(np.float64) ** 2

    power_sum /= (n_segments * n_channels)

    # Spectral edge: find where 95% of cumulative energy is reached
    cumsum = np.cumsum(power_sum)
    total_energy = cumsum[-1]

    if total_energy <= 0:
        return math.floor(sample_rate / 2)

    edge_idx = int(np.searchsorted(cumsum, 0.95 * total_energy))
    freq_resolution = sample_rate / coarse_nfft
    frequency_max = edge_idx * freq_resolution

    frequency_max *= padding_factor

    if pretty_mode:
        if frequency_max < 1000:
            nearest = 250
        elif frequency_max < 2000:
            nearest = 500
        else:
            nearest = 1000
        frequency_max = nearest * math.ceil(frequency_max / nearest)

    frequency_max = min(frequency_max, math.floor(sample_rate / 2))

    return max(frequency_max, 1)


def calculate_optimal_nfft(sample_rate: int, frequency_max: float,
                           panel_height: float, window_size: int) -> int:
    """Calculate the optimal nfft for a given display resolution and frequency range.

    Targets approximately 1 frequency bin per pixel in the displayed frequency
    range after any audio resampling, while respecting the minimum window_size
    constraint and rounding up to the next power of 2 for FFT efficiency.
    """
    if frequency_max <= 0 or panel_height <= 0:
        return window_size

    nyquist = sample_rate / 2
    target_nfft = panel_height * nyquist / frequency_max

    nfft = 1 << math.ceil(math.log2(max(1, target_nfft)))

    return max(window_size, nfft)


def peak_envelope(es_audio: es.audio.Audio, start: int = 0, end: int = None, padding: int = 0,
                  window_size: int = None, step_size: int = None) -> Envelope:
    return Envelope(es_audio=es_audio, mode=EnvelopeModes.PEAK, start=start, end=end, padding=padding,
               window_size=window_size, step_size=step_size)


def rms_envelope(es_audio: es.audio.Audio, start: int = 0, end: int = None, padding: int = 0,
                  window_size: int = None, step_size: int = None) -> Envelope:
    return Envelope(es_audio=es_audio, mode=EnvelopeModes.RMS, start=start, end=end, padding=padding,
               window_size=window_size, step_size=step_size)


def spectrogram(es_audio: es.audio.Audio) -> Spectrogram:
    return Spectrogram(es_audio=es_audio)


def _on_config_updated():
    if es.cfg['analysis.window-overlap'] is None:
        es.cfg['analysis.window-overlap'] = 3 * es.cfg['analysis.window-size'] // 4

    # Set a 4x fallback for nfft (used when the analysis module is called
    # directly, outside a visualization entry point). Visualization entry
    # points override this with a resolution-aware value via set_optimal_nfft.
    # nfft_auto tracks whether the user explicitly set nfft — if so, the
    # resolution-aware override is skipped.
    global nfft_auto
    if es.cfg['analysis.spectrogram.nfft'] is None:
        es.cfg['analysis.spectrogram.nfft'] = 4 * es.cfg['analysis.window-size']
        nfft_auto = True
    else:
        nfft_auto = False


es.add_event_listener('config.updated', _on_config_updated)
