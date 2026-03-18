"""A module to load audio files and manage audio data"""
import math
import os
import typing

import estimpy as es
import numpy as np
import pydub
import scipy


def compute_ramp_gain(t: float, t_start: float, t_end: float, level: float, shape: float) -> float:
    """Compute the ramp gain multiplier at a given time.

    :param t: Current time in seconds.
    :param t_start: Time when the ramp begins (gain is at its minimum).
    :param t_end: Time when the ramp ends (gain reaches 1.0).
    :param level: Reduction percentage at ramp start (0-100). 0 = no reduction, 100 = silence.
    :param shape: Exponential easing parameter k. 0 = linear, negative = fast rise then slow,
        positive = slow rise then fast. Curve: (e^(kt)-1)/(e^k-1).
    :return float: Gain multiplier between 0.0 and 1.0.
    """
    if level <= 0 or t >= t_end:
        return 1.0

    start_gain = 1.0 - min(level, 100) / 100.0

    if t <= t_start:
        return start_gain

    progress = (t - t_start) / (t_end - t_start)

    if shape == 0:
        eased = progress
    else:
        eased = (math.exp(shape * progress) - 1) / (math.exp(shape) - 1)

    return start_gain + (1.0 - start_gain) * eased


class Audio:
    def __init__(self, file: str = None, audio_format: str = None, audio_data: np.ndarray = None,
                 sample_rate: int = None, bit_depth: int = None, metadata: dict = None):
        """
        :param file:
        :param audio_format:
        :param audio_data:
        :param sample_rate:
        :param bit_depth:
        :param metadata:
        """
        self._metadata = es.metadata.Metadata(metadata=metadata)

        if file is not None:
            _, audio_format = os.path.splitext(file)
            audio_format = audio_format[1:]

            audio_segment = pydub.AudioSegment.from_file(file)

            sample_rate = audio_segment.frame_rate
            # sample_width is the number of bytes per sample, so multiply by 8 to get bits
            bit_depth = 8 * audio_segment.sample_width

            # Convert to numpy array with each channel in its own row. Since get_array_of_samples() returns 1D
            # interleaved vector (so [c1_1, c2_1, c1_2, c2_2, etc.]), we need to use reshape with
            # F-contiguous ordering to get the data from each channel into its own row
            audio_data = np.ascontiguousarray(np.array(
                audio_segment.get_array_of_samples()).reshape((audio_segment.channels, -1),
                                                              order='F'))

            file_metadata = es.metadata.Metadata(file=file)
            self._metadata.set_metadata(file_metadata.get_metadata())
            self._metadata.set_file(file)

        if audio_data is not None:
            # Since we will be frequently slicing subsets of audio data from each channel, it will be more efficient
            # to store the audio data as C-contiguous ordering
            audio_data = np.ascontiguousarray(audio_data)

            # Normalize audio data from 0 to 1 based upon the bitdepth of the file
            # so divide by 2 to the power of the bit depth minus 1 (since signed int).
            # Use float32 to halve memory usage — sufficient precision for visualization and analysis.
            audio_data = np.divide(audio_data, 2 ** (bit_depth - 1), dtype=np.float32)

        self._file = file  # type: str
        self._source_file = file  # type: str
        self._format = audio_format  # type: str

        self._sample_rate = sample_rate  # type int
        self._bit_depth = bit_depth  # type: int

        self._data = audio_data  # type: np.ndarray[typing.Type[float]]
        self._channels = audio_data.shape[0] if audio_data is not None else 0  # type: int
        self._sample_count = audio_data.shape[1] if audio_data is not None else 0  # type: int

    def __str__(self):
        return self.get_string()

    @property
    def bit_depth(self) -> int:
        """
        :return int: The bit depth of the raw audio data
        """
        return self._bit_depth

    @property
    def channels(self) -> int:
        """
        :return int: The number of channels (i.e. rows) in the audio data
        """
        return self._channels

    @property
    def data(self) -> np.ndarray[typing.Type[float]]:
        """
        :return: np.ndarray[typing.Type[float]]: A 2-dimensional array of audio samples with channels as rows and time
                                                 as columns. This form of the data is floats between 0 and 1,
                                                 and is suitable for analysis and visualization.
                                                 This array is C-contiguous.
        """
        return self._data

    @property
    def data_raw(self) -> np.ndarray[typing.Type[int]]:
        """
        :return np.ndarray[typing.Type[int]]: A 2-dimensional array of audio samples with channels as rows and time
                                              as columns. This form of the data is integers of size specified
                                              by bit_depth, and is suitable for writing to files and realtime playback.
                                              Reconstructed on demand from normalized data to avoid storing a
                                              separate copy in memory.
        """
        if self._data is None:
            return None
        dtype = np.int16 if self._bit_depth <= 16 else np.int32
        scale = 2 ** (self._bit_depth - 1)
        return np.ascontiguousarray(
            (self._data * scale).clip(-scale, scale - 1).astype(dtype)
        )

    @property
    def file(self) -> str:
        """
        :return str: The path to the audio file used for playback and encoding.
        """
        return self._file

    @property
    def source_file(self) -> str:
        """
        :return str: The path to the original source file (before any processing).
        """
        return self._source_file

    @property
    def format(self) -> str:
        """
        :return str: The format of the audio file
        """
        return self._format

    @property
    def length(self) -> float:
        """
        :return float: The length of the audio (in seconds)
        """
        return self.sample_count / self.sample_rate

    @property
    def metadata(self) -> es.metadata.Metadata | None:
        """
        :return es.metadata.Metadata | None:
        """
        return self._metadata

    @property
    def sample_rate(self) -> int:
        """
        :return int:
        """
        return self._sample_rate

    @property
    def sample_count(self) -> int:
        """
        :return int:
        """
        return self._sample_count

    def get_string(self) -> str:
        string = self.metadata.title

        if self.metadata.artist:
            string = f'{self.metadata.artist} - {string}'

        return string

    def resample(self, new_sample_rate: int) -> None:
        """Resamples audio data to a new sample rate for the instance
        :param int new_sample_rate:
        :return None:
        """
        self._data = resample_audio_data(self._data, self.sample_rate, new_sample_rate)
        self._sample_rate = new_sample_rate
        self._sample_count = self._data.shape[1]

    def save_metadata(self) -> None:
        """Save metadata to the audio file for the instance
        :return None:
        """
        if self.file is None:
            raise Exception('Error saving metadata: No file name specified for audio.')
        elif not os.path.isfile(self.file):
            raise Exception(f'Error saving metadata: File {self.file} does not exist.')

        self.metadata.save()

    def _clone_with_data(self, data: np.ndarray, temp_name: str) -> 'Audio':
        """Create a new Audio instance with new data and a temp WAV file for FFmpeg.

        Handles the common pattern of: convert normalized data to raw integers,
        write to a temp WAV, and construct a new Audio with all the same metadata.

        :param data: New normalized float32 audio data (channels, samples).
        :param temp_name: Filename for the temp WAV file.
        :return Audio: New Audio instance backed by the temp WAV.
        """
        temp_path = es.utils.get_temp_file_path(temp_file_name=temp_name)
        dtype = np.int16 if self._bit_depth <= 16 else np.int32
        scale = 2 ** (self._bit_depth - 1)
        raw = (data * scale).clip(-scale, scale - 1).astype(dtype)
        scipy.io.wavfile.write(temp_path, self.sample_rate, raw.T)
        es.utils.add_temp_file(temp_path)

        audio = Audio.__new__(Audio)
        audio._metadata = self._metadata
        audio._file = temp_path
        audio._source_file = self._source_file
        audio._format = 'wav'
        audio._sample_rate = self._sample_rate
        audio._bit_depth = self._bit_depth
        audio._data = np.ascontiguousarray(data)
        audio._channels = self._channels
        audio._sample_count = self._sample_count
        return audio

    def with_frequency_transform(self) -> 'Audio':
        """Create a new Audio with frequency content shifted and/or scaled.

        Uses two complementary techniques to transform frequency content while
        preserving duration:

        - **Scale** (f → f × scale): Full-signal FFT with forward bin mapping.
          Each source bin's complex coefficient is distributed to the scaled target
          position, preserving both magnitude and phase. Harmonic relationships are
          maintained.

        - **Shift** (f → f + shift): Hilbert transform / single-sideband (SSB)
          modulation. Multiplies the analytic signal by exp(j·2π·Δf·t), which
          translates all frequency content by a constant offset. Harmonic
          relationships are NOT preserved (intervals change).

        When both are active, scaling is applied first, then shifting.

        Transform parameters are read from config:
        - audio.frequency.scale: multiplicative factor (1 = no change)
        - audio.frequency.shift: additive offset in Hz (0 = no change)

        Content pushed above Nyquist or below 0 Hz is discarded.

        :return Audio: A new Audio instance with transformed data and a temp WAV file.
        """
        scale = es.cfg['audio.frequency.scale']
        shift = es.cfg['audio.frequency.shift']

        if scale == 1 and shift == 0:
            return self

        transformed_channels = []

        for ch in range(self._channels):
            channel_data = self._data[ch]

            # Step 1: Frequency scaling via FFT forward bin mapping
            if scale != 1:
                X = scipy.fft.rfft(channel_data)
                n_bins = len(X)
                Y = np.zeros(n_bins, dtype=np.complex128)

                src_bins = np.arange(n_bins)
                targets = src_bins * scale
                valid = targets < n_bins
                src_valid = src_bins[valid]
                targets_valid = targets[valid]
                low_bins = targets_valid.astype(int)
                fracs = targets_valid - low_bins

                np.add.at(Y, low_bins, (1 - fracs) * X[src_valid])

                high_bins = low_bins + 1
                high_valid = high_bins < n_bins
                np.add.at(Y, high_bins[high_valid], fracs[high_valid] * X[src_valid[high_valid]])

                channel_data = scipy.fft.irfft(Y, n=self._sample_count).astype(np.float32)

            # Step 2: Frequency shifting via Hilbert SSB modulation
            if shift != 0:
                t = np.arange(self._sample_count) / self._sample_rate
                analytic = scipy.signal.hilbert(channel_data)
                channel_data = np.real(analytic * np.exp(1j * 2 * np.pi * shift * t)).astype(np.float32)

            transformed_channels.append(channel_data)

        transformed = np.vstack(transformed_channels)
        return self._clone_with_data(transformed, 'freq_transform_audio.wav')

    def with_stereo_stim(self) -> 'Audio':
        """Create a new Audio with stereo stim filters applied.

        Applies a bandpass Butterworth filter to remove DC offset, subsonic content,
        and high-frequency content that could be harmful with direct-output stereostim
        devices. Uses zero-phase filtering to preserve timing relationships.

        Filter cutoffs are read from config:
        - audio.stereo-stim.high-pass (default 20 Hz)
        - audio.stereo-stim.low-pass (default 12000 Hz)

        :return Audio: A new Audio instance with filtered data and a temp WAV file
        """
        hp = es.cfg['audio.stereo-stim.high-pass']
        lp = es.cfg['audio.stereo-stim.low-pass']

        # Design bandpass Butterworth filter (4th order, zero-phase doubles effective order to 8th)
        sos = scipy.signal.butter(4, [hp, lp], btype='bandpass', fs=self.sample_rate, output='sos')
        filtered = scipy.signal.sosfiltfilt(sos, self._data, axis=1).astype(np.float32)
        return self._clone_with_data(filtered, 'ss_audio.wav')

    def with_ramp(self, t_start: float = 0.0) -> 'Audio':
        """Create a new Audio with an amplitude ramp applied.

        Applies a gain envelope that ramps from a reduced level at t_start up to full
        amplitude at the end of the file. The ramp shape is controlled by an exponential
        easing parameter.

        Ramp parameters are read from config:
        - audio.ramp.level (0-100): percentage reduction at ramp start
        - audio.ramp.shape: exponential easing parameter k (0 = linear)

        :param t_start: Time in seconds where the ramp begins (default 0.0).
        :return Audio: A new Audio instance with ramped data and a temp WAV file.
        """
        level = es.cfg['audio.ramp.level']
        shape = es.cfg['audio.ramp.shape']

        if level <= 0:
            return self

        # Build gain envelope across all samples (vectorized)
        t_end = self.length
        start_gain = 1.0 - min(level, 100) / 100.0
        times = np.linspace(t_start, t_end, self._sample_count, endpoint=False, dtype=np.float32)

        # Compute normalized progress [0, 1] for samples within the ramp region
        progress = np.clip((times - t_start) / (t_end - t_start), 0.0, 1.0)

        if shape == 0:
            eased = progress
        else:
            eased = (np.exp(shape * progress) - 1) / (math.exp(shape) - 1)

        gains = np.where(times >= t_end, 1.0, start_gain + (1.0 - start_gain) * eased).astype(np.float32)
        ramped = self._data * gains[np.newaxis, :]
        return self._clone_with_data(ramped, 'ramp_audio.wav')

    def with_triphase(self) -> 'Audio':
        """Create a 3-channel Audio with channels [A, B, -(A+B)] for triphase visualization.

        The triphase channel -(A+B) represents the signal at the common ground electrode
        in a 3-electrode estim setup. By Kirchhoff's current law, the current at the
        common node equals the negated sum of the currents from the two signal electrodes.

        :return Audio: A new Audio instance with 3 channels
        """
        if self.channels != 2:
            raise ValueError("Triphase requires stereo audio")

        triphase_float = -(self.data[0] + self.data[1])

        audio = Audio.__new__(Audio)
        audio._metadata = self._metadata
        audio._file = self._file
        audio._source_file = self._source_file
        audio._format = self._format
        audio._sample_rate = self._sample_rate
        audio._bit_depth = self._bit_depth
        audio._data = np.ascontiguousarray(np.vstack([self.data, triphase_float.reshape(1, -1)]))
        audio._channels = 3
        audio._sample_count = self._sample_count
        return audio

    def time_to_data_index(self, time: float) -> int | None:
        """Converts a time (in seconds) from the start of the audio to the corresponding time index in the audio data
        :param float time:
        :return int | None:
        """
        index = math.floor(time * self.sample_rate)

        if index < 0 or index >= self.sample_count:
            return None
        else:
            return index


def resample_audio_data(audio_data: np.ndarray, sample_rate: int, new_sample_rate: int) -> np.ndarray:
    """Resamples audio data to a new sample rate
    :param np.ndarray audio_data: A 2-dimensional array of audio samples with channels as rows and time as columns.
    :param int sample_rate: The sample rate of audio_data
    :param int new_sample_rate: The new sample rate
    :return np.ndarray: audio_data resampled to the specified sample rate
    """
    lcm = math.lcm(sample_rate, new_sample_rate)

    return np.ascontiguousarray(
        scipy.signal.resample_poly(audio_data, up=lcm // sample_rate, down=lcm // new_sample_rate, axis=1))
