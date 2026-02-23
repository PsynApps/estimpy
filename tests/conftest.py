import copy
import os
import tempfile
import wave

import numpy as np
import pytest

import estimpy as es
from estimpy.audio import Audio


TEST_INPUT_DIR = os.path.join(os.path.dirname(__file__), 'input')
TEST_WAV = os.path.join(TEST_INPUT_DIR, 'test.wav')

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
def tmp_wav_file():
    """Write a temporary stereo WAV file and return its path. Cleaned up after test."""
    t = np.linspace(0, DURATION, N_SAMPLES, endpoint=False)
    left = (np.sin(2 * np.pi * 440 * t) * 0.8 * 32767).astype(np.int16)
    right = (np.sin(2 * np.pi * 880 * t) * 0.8 * 32767).astype(np.int16)
    interleaved = np.empty(2 * N_SAMPLES, dtype=np.int16)
    interleaved[0::2] = left
    interleaved[1::2] = right

    fd, path = tempfile.mkstemp(suffix='.wav')
    os.close(fd)

    with wave.open(path, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(interleaved.tobytes())

    yield path

    if os.path.exists(path):
        os.remove(path)
