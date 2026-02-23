import os
import tempfile
import warnings

import numpy as np
import pytest

import estimpy as es
from estimpy.utils import (
    get_output_file,
    get_temp_file_path,
    log10_quiet,
    seconds_to_string,
)


class TestSecondsToString:
    def test_zero(self):
        assert seconds_to_string(0) == '0:00'

    def test_seconds_only(self):
        assert seconds_to_string(45) == '0:45'

    def test_minutes_and_seconds(self):
        assert seconds_to_string(125) == '2:05'

    def test_hours(self):
        assert seconds_to_string(3661) == '1:01:01'

    def test_days(self):
        assert seconds_to_string(90061) == '1:01:01:01'

    def test_fractional_truncated(self):
        assert seconds_to_string(61.9) == '1:01'


class TestLog10Quiet:
    def test_positive_values(self):
        result = log10_quiet(np.array([1.0, 10.0, 100.0]))
        np.testing.assert_allclose(result, [0.0, 1.0, 2.0])

    def test_zero_no_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            result = log10_quiet(np.array([0.0]))
        assert np.isneginf(result[0])

    def test_scalar(self):
        result = log10_quiet(100)
        assert result == 2.0

    def test_array_preserves_shape(self):
        arr = np.ones((3, 4))
        result = log10_quiet(arr)
        assert result.shape == (3, 4)


class TestGetOutputFile:
    def test_directory_input(self, tmp_path):
        result = get_output_file(str(tmp_path), 'song.mp3', 'png')
        assert result.endswith('song.png')
        assert str(tmp_path) in result

    def test_explicit_file_path(self, tmp_path):
        output = str(tmp_path / 'custom_name.png')
        result = get_output_file(output, 'song.mp3', 'png')
        assert result.endswith('custom_name.png')

    def test_format_extension(self, tmp_path):
        result = get_output_file(str(tmp_path), 'audio.wav', 'mp4')
        assert result.endswith('.mp4')


class TestGetTempFilePath:
    def test_without_filename(self):
        result = get_temp_file_path()
        assert result == tempfile.gettempdir()

    def test_with_filename(self):
        result = get_temp_file_path('test_file.tmp')
        assert result.endswith('test_file.tmp')
        assert tempfile.gettempdir() in result
