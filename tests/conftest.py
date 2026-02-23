import copy
import os
import shutil
import tempfile

import numpy as np
import pytest

import estimpy as es
from estimpy.audio import Audio


TEST_INPUT_DIR = os.path.join(os.path.dirname(__file__), 'input')
TEST_MP3 = os.path.join(TEST_INPUT_DIR, 'test.mp3')

SAMPLE_RATE = 44100
DURATION = 1.0
N_SAMPLES = int(SAMPLE_RATE * DURATION)


@pytest.fixture(autouse=True)
def config_reset():
    """Save and restore es.cfg around each test to prevent cross-test contamination."""
    saved_cfg = copy.deepcopy(es.cfg)
    saved_base_cfg = copy.deepcopy(es.base_cfg)
    yield
    es.cfg.clear()
    es.cfg.update(saved_cfg)
    es.base_cfg.clear()
    es.base_cfg.update(saved_base_cfg)


@pytest.fixture
def synthetic_stereo_audio():
    """1-second stereo Audio: 440Hz left, 880Hz right, 44100Hz 16-bit."""
    t = np.linspace(0, DURATION, N_SAMPLES, endpoint=False)
    left = (np.sin(2 * np.pi * 440 * t) * 0.8 * 32767).astype(np.int16)
    right = (np.sin(2 * np.pi * 880 * t) * 0.8 * 32767).astype(np.int16)
    audio_data = np.vstack([left, right])
    return Audio(audio_data=audio_data, sample_rate=SAMPLE_RATE, bit_depth=16)


@pytest.fixture
def synthetic_mono_audio():
    """1-second mono Audio: 440Hz sine, 44100Hz 16-bit."""
    t = np.linspace(0, DURATION, N_SAMPLES, endpoint=False)
    mono = (np.sin(2 * np.pi * 440 * t) * 0.8 * 32767).astype(np.int16)
    audio_data = mono.reshape(1, -1)
    return Audio(audio_data=audio_data, sample_rate=SAMPLE_RATE, bit_depth=16)


@pytest.fixture
def tmp_mp3_file():
    """Copy test.mp3 to a temp file for destructive tests. Cleaned up after test."""
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    shutil.copy2(TEST_MP3, path)

    yield path

    if os.path.exists(path):
        os.remove(path)
