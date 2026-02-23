import os

import numpy as np
import pytest

from estimpy.audio import Audio
from estimpy.metadata import Metadata
from tests.conftest import TEST_WAV, TEST_MP3, SAMPLE_RATE


class TestAudioLoadWav:
    def test_load_wav_channels(self):
        audio = Audio(file=TEST_WAV)
        assert audio.channels == 2

    def test_load_wav_sample_rate(self):
        audio = Audio(file=TEST_WAV)
        assert audio.sample_rate == SAMPLE_RATE

    def test_load_wav_length(self):
        audio = Audio(file=TEST_WAV)
        assert abs(audio.length - 1.0) < 0.01

    def test_load_wav_bit_depth(self):
        audio = Audio(file=TEST_WAV)
        assert audio.bit_depth == 16

    def test_load_wav_format(self):
        audio = Audio(file=TEST_WAV)
        assert audio.format == 'wav'


class TestAudioLoadMp3:
    def test_load_mp3_channels(self):
        audio = Audio(file=TEST_MP3)
        assert audio.channels == 2

    def test_load_mp3_sample_rate(self):
        audio = Audio(file=TEST_MP3)
        assert audio.sample_rate == SAMPLE_RATE

    def test_load_mp3_length_positive(self):
        audio = Audio(file=TEST_MP3)
        assert audio.length > 0

    def test_load_mp3_format(self):
        audio = Audio(file=TEST_MP3)
        assert audio.format == 'mp3'

    def test_load_mp3_data_normalized(self):
        audio = Audio(file=TEST_MP3)
        assert audio.data.min() >= -1.0
        assert audio.data.max() <= 1.0

    def test_load_mp3_data_float32(self):
        audio = Audio(file=TEST_MP3)
        assert audio.data.dtype == np.float32


class TestAudioFileProperties:
    def test_file_property_wav(self):
        audio = Audio(file=TEST_WAV)
        assert audio.file == TEST_WAV

    def test_file_property_mp3(self):
        audio = Audio(file=TEST_MP3)
        assert audio.file == TEST_MP3

    def test_metadata_populated(self):
        audio = Audio(file=TEST_MP3)
        assert isinstance(audio.metadata, Metadata)

    def test_get_string_has_title(self):
        audio = Audio(file=TEST_MP3)
        s = audio.get_string()
        assert isinstance(s, str)
        assert len(s) > 0


class TestAudioResample:
    def test_resample_changes_sample_rate(self):
        audio = Audio(file=TEST_WAV)
        original_rate = audio.sample_rate
        audio.resample(22050)
        assert audio.sample_rate == 22050
        assert audio.sample_rate != original_rate

    def test_resample_updates_data_shape(self):
        audio = Audio(file=TEST_WAV)
        original_samples = audio.sample_count
        audio.resample(22050)
        # Halving sample rate should roughly halve the sample count
        assert abs(audio.sample_count - original_samples // 2) <= 1

    def test_resample_preserves_channels(self):
        audio = Audio(file=TEST_WAV)
        original_channels = audio.channels
        audio.resample(22050)
        assert audio.channels == original_channels


class TestMetadataFileIO:
    def test_load_mp3_format_detection(self):
        meta = Metadata(file=TEST_MP3)
        assert meta.format == 'mp3'

    def test_load_mp3_has_title(self):
        meta = Metadata(file=TEST_MP3)
        # Title comes from either ID3 tags or filename parsing
        assert meta.title is not None

    def test_load_mp3_default_genre(self):
        meta = Metadata(file=TEST_MP3)
        # Genre should be set (either from file or default)
        assert meta.genre is not None

    def test_filename_parsing_artist_title(self):
        meta = Metadata()
        result = meta._get_metadata_from_file_path(TEST_MP3)
        # test.mp3 doesn't match "artist - title" pattern, so title should be filename
        assert 'title' in result

    def test_save_roundtrip(self, tmp_mp3_file):
        # Load, modify, save, reload, verify
        meta = Metadata(file=tmp_mp3_file)
        meta.title = 'Test Title Modified'
        meta.save()

        meta2 = Metadata(file=tmp_mp3_file)
        assert meta2.title == 'Test Title Modified'

    def test_save_unsupported_format_raises(self):
        meta = Metadata()
        meta.set_file('fake.wav')
        with pytest.raises(Exception, match='Unsupported'):
            meta.save()

    def test_save_no_file_raises(self):
        meta = Metadata()
        with pytest.raises(Exception, match='No filename'):
            meta.save()

    def test_save_artist_roundtrip(self, tmp_mp3_file):
        meta = Metadata(file=tmp_mp3_file)
        meta.artist = 'Test Artist'
        meta.save()

        meta2 = Metadata(file=tmp_mp3_file)
        assert meta2.artist == 'Test Artist'
