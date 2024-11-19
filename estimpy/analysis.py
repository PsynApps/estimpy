"""A module for analysis of audio data"""
import enum
import math
import typing

import estimpy as es
import numpy as np
import scipy


class EnvelopeModes(enum.StrEnum):
    PEAK = 'peak'
    RMS = 'rms'


class Envelope:
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

        def window_function(window: np.ndarray):
            if mode == EnvelopeModes.PEAK:
                return np.max(window)
            elif mode == EnvelopeModes.RMS:
                return np.sqrt(np.mean(window))
            else:
                return 0

        self._envelope_data = np.array([[window_function(audio_data[j, i:i + window_size])
                                         for i in range(start, end, step_size)]
                                        for j in range(es_audio.channels)])

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
    def __init__(self, es_audio: es.audio.Audio, frequency_min: int = None, frequency_max: int = None):
        """
        :param es_audio:
        :param frequency_min:
        :param frequency_max:
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
    def frequencies(self) -> np.ndarray[typing.Type[float]]:
        """
        :return np.ndarray[typing.Type[float]]:
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
    def spectrogram_data(self) -> np.ndarray[typing.Type[float]]:
        """
        :return np.ndarray[typing.Type[float]]:
        """
        return self._spectrogram_data

    @property
    def times(self) -> np.ndarray[typing.Type[float]]:
        """
        :return np.ndarray[typing.Type[float]]:
        """
        return self._times

    @classmethod
    def generate_spectrogram_data(cls, audio_data: np.ndarray, sample_rate: int, window_function: str = None,
                                  window_size: int = None, window_overlap: int = None, nfft: int = None,
                                  frequency_min: float = None, frequency_max: float = None,
                                  scaling: SpectrogramScaling = SpectrogramScaling.DB) -> \
                                      typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        :param audio_data:
        :param sample_rate:
        :param window_function:
        :param window_size:
        :param window_overlap:
        :param nfft:
        :param frequency_min:
        :param frequency_max:
        :param scaling:
        :return:
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
            nfft = es.cfg['analysis.spectrogram.nfft']

        if frequency_min is None:
            frequency_min = es.cfg['analysis.spectrogram.frequency-min']

        if frequency_max is None:
            # If frequency max is not defined in config, use the nyquist limit (this function does not autoscale)
            frequency_max = es.cfg['analysis.spectrogram.frequency-max']\
                if es.cfg['analysis.spectrogram.frequency-max'] is not None else math.floor(sample_rate / 2)

        nfft = max(nfft, window_size)

        # Multichannel
        for i in range(audio_data.shape[0]):
            frequencies, times, spectrogram_channel = scipy.signal.spectrogram(
                audio_data[i, :].T,
                fs=sample_rate,
                window=window_function,
                nperseg=window_size,
                noverlap=window_overlap,
                nfft=nfft,
                scaling='spectrum',
                mode='magnitude'
            )
            # Convert channel to 3d matrix with the first dimension as the channel_id
            spectrogram_channel = spectrogram_channel.reshape(1, *spectrogram_channel.shape)

            if spectrogram_data is None:
                spectrogram_data = spectrogram_channel
            else:
                # Append all channels on to the first
                spectrogram_data = np.append(spectrogram_data, spectrogram_channel, axis=0)

        # Trim spectrogram to only include specified frequency range
        # Find the indicies which correspond to the desired frequency range
        frequency_step = frequencies[1] - frequencies[0]
        i_frequency_min = math.floor(frequency_min / frequency_step)
        i_frequency_max = min(math.ceil(frequency_max / frequency_step) + 1, len(frequencies) - 1)

        frequencies = frequencies[i_frequency_min:i_frequency_max]

        # Trim spectrogram to the desired frequency range
        if len(audio_data.shape) == 1:
            spectrogram_data = spectrogram_data[i_frequency_min:i_frequency_max, :]
        else:
            spectrogram_data = spectrogram_data[:, i_frequency_min:i_frequency_max, :]

        if scaling == SpectrogramScaling.DB:
            spectrogram_data = 20 * es.utils.log10_quiet(spectrogram_data)

        return frequencies, times, spectrogram_data

    @classmethod
    def _get_frequency_max(cls, audio_data: np.ndarray, sample_rate: int,
                           method: SpectrogramFrequencyMaxMethods = None,
                           padding_factor: float = None, pretty_mode: bool = True):
        if method is None:
            method = SpectrogramFrequencyMaxMethods(es.cfg['analysis.spectrogram.frequency-max-method'])

        if padding_factor is None:
            padding_factor = es.cfg['analysis.spectrogram.frequency-max-padding-factor']

        frequencies, times, spectrogram_data = cls.generate_spectrogram_data(audio_data, sample_rate,
                                                                             scaling=SpectrogramScaling.LINEAR)
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

            # Initialize vectors to store spectral edge frequency indicies for each time bin
            spec_edge80_indices = np.zeros(spectral_cumsum.shape[1])
            spec_edge95_indices = np.zeros(spectral_cumsum.shape[1])

            for i_t in range(spectral_cumsum.shape[1]):
                # Calculate the 80% and 95% spectral edge frequencies for each time bin
                spec_edge80_indices[i_t] = np.argmax(
                    spectral_cumsum[:, i_t] >= 0.8 * spectral_cumsum[frequency_max_index, i_t])
                spec_edge95_indices[i_t] = np.argmax(
                    spectral_cumsum[:, i_t] >= 0.95 * spectral_cumsum[frequency_max_index, i_t])

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
            power_threshold = 0.2 * -es.cfg['analysis.spectrogram.dynamic-range']
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
        es.cfg['analysis.window-overlap'] = es.cfg['analysis.window-size'] // 2

    if es.cfg['analysis.spectrogram.nfft'] is None:
        es.cfg['analysis.spectrogram.nfft'] = es.cfg['analysis.window-size']


es.add_event_listener('config.updated', _on_config_updated)
