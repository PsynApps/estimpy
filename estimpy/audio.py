"""A module to load audio files and manage audio data"""
import math
import os
import typing

import estimpy as es
import numpy as np
import pydub
import scipy


class Audio:
    def __init__(self, file: str = None, format: str = None, audio_data: np.ndarray = None,
                 sample_rate: int = None, bit_depth: int = None, metadata: dict = None):
        """
        :param file:
        :param format:
        :param audio_data:
        :param sample_rate:
        :param bit_depth:
        :param metadata:
        """
        self._metadata = es.metadata.Metadata(metadata=metadata)

        if file is not None:
            _, format = os.path.splitext(file)
            format = format[1:]

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
        self._format = format  # type: str

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
        return np.ascontiguousarray(
            (self._data * (2 ** (self._bit_depth - 1))).clip(
                -(2 ** (self._bit_depth - 1)), 2 ** (self._bit_depth - 1) - 1
            ).astype(dtype)
        )

    @property
    def file(self) -> str:
        """
        :return str: The path to the file
        """
        return self._file

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
        self._data = resample_audio_data(self.sample_rate, new_sample_rate)
        self._sample_rate = new_sample_rate

    def save_metadata(self) -> None:
        """Save metadata to the audio file for the instance
        :return None:
        """
        if self.file is None:
            raise Exception('Error saving metadata: No file name specified for audio.')
        elif not os.path.isfile(self.file):
            raise Exception(f'Error saving metadata: File {self.file} does not exist.')

        self.metadata.save()

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
        scipy.signal.resample_poly(audio_data, up=lcm / sample_rate, down=lcm / new_sample_rate, axis=1))
