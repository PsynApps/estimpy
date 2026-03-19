"""Low-level audio playback via pygame-ce's SDL2 mixer.

Provides module-level functions for loading, playing, stopping, and volume
control of audio channels. Uses daemon threads for smooth volume ramping.
Per-channel stereo panning is handled by routing each logical channel to a
separate pygame Channel with left/right volume set accordingly.

Note: module-level globals preclude multiple simultaneous players, which is
acceptable since the application is single-player by design.
"""
import os
import threading
import time
import typing

import estimpy as es
import numpy as np
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = ''
import pygame


# pygame's use of playing vs. pausing is rather confusing. To start playback for the first time,
# play() must be used (unpause() cannot be used). If a file is paused,
# unpause() must be used to resume (play() will restart from the beginning).
_initialized = False  # type: bool
_is_playing = False  # type: bool
_audio_time = 0  # type: float
_clock_time = 0  # type: float
_volume_thread_times = []  # type: typing.List[float]

_channels = []  # type: typing.List[pygame.mixer.Channel]
_volumes = []  # type: typing.List[float]

_es_audio = None  # type: es.audio.Audio | None
_ramp_gain = 1.0  # type: float


def get_time() -> float:
    """Return the current playback position in seconds, accounting for looping."""
    global _audio_time, _clock_time

    if is_playing():
        # get_pos() returns milliseconds
        audio_time_current = _audio_time + time.time() - _clock_time
        # Taking the modulus of the position with the length allows us to support looping
        return audio_time_current % _es_audio.length
    else:
        return 0


def get_current_volume(channel: int) -> float:
    """Get the current actual volume for a channel (reflects smoothing ramp)."""
    return _volumes[channel]


def get_ramp_gain() -> float:
    """Return the current ramp gain multiplier (0.0 to 1.0)."""
    return _ramp_gain


def set_ramp_gain(gain: float) -> None:
    """Set the ramp gain multiplier applied to all channel volumes.

    Called each frame by the player window to modulate volume in real-time
    without reprocessing audio data. Immediately applies the new gain to all
    active channels so the volume change takes effect without waiting for a
    volume ramp thread.

    :param gain: Gain multiplier (0.0 to 1.0).
    """
    global _ramp_gain
    _ramp_gain = max(0.0, min(1.0, gain))
    # Apply immediately to all active channels at their current volume
    if _is_playing and _channels:
        for i in range(len(_channels)):
            _set_channel_volume_unsafe(volume=_volumes[i], channel=i)


def initialize() -> None:
    """Initialize volume and thread-time arrays for the maximum supported channel count."""
    global _volumes, _volume_thread_times

    max_channels = 3  # stereo (2) + triphase (3)

    _volumes = [es.cfg['player.volume-start']] * max_channels
    _volume_thread_times = [0] * max_channels


def is_playing() -> bool:
    """Return True if audio is actively playing (started and channels still producing output)."""
    if not _is_playing:
        return False
    if not _channels:
        return False
    return any(ch.get_busy() for ch in _channels)


def load(es_audio: es.audio.Audio):
    """Set the audio source for subsequent play() calls. Initializes on first call."""
    global _es_audio, _initialized

    if not _initialized:
        initialize()
        _initialized = True

    _es_audio = es_audio


def play(audio_time: float = 0, target_volumes: typing.List[float] = None):
    """Start playback from the given position with a smooth volume ramp-in.

    :param audio_time: Position in seconds to start from.
    :param target_volumes: Per-channel target volumes (0-100) for the ramp-in.
        If None, uses the current ``_volumes`` values.
    """
    global _is_playing, _audio_time, _clock_time, _channels, _volumes

    if _is_playing:
        stop()

    sample_time = _es_audio.time_to_data_index(audio_time)

    # Use a small audio buffer (256 samples) so that volume changes via
    # set_volume() take effect every ~5.8ms instead of every ~11.6ms (default
    # 512). This doubles the granularity of fade-to-zero transitions in stop(),
    # making individual volume steps small enough (~6%) to be inaudible.
    # Always use 16-bit signed audio for playback. The data_raw property
    # converts normalized float data back to integers, and pygame only
    # supports 8-bit and 16-bit sizes.
    pygame.mixer.init(frequency=_es_audio.sample_rate, size=-16, channels=2, buffer=256)

    repeat_mode = _get_repeat_mode()
    loops = -1 if repeat_mode == 'one' else 0

    _channels = []

    # _is_playing must be set to true so that the set_volume() calls for each channel work correctly
    _is_playing = True

    # Prepare Sound objects
    for channel in range(_es_audio.channels):
        _channels.append(pygame.mixer.Channel(channel))

        # Convert to 16-bit for playback (data_raw may return int32 for high bit-depth files).
        # Even though we are playing through just one channel, Sound() buffer expects interleaved stereo audio
        # data, so we have to duplicate every sample.
        raw_samples = _es_audio.data_raw[channel, sample_time:]
        if raw_samples.dtype != np.int16:
            raw_samples = np.clip(raw_samples, -32768, 32767).astype(np.int16)
        sound = pygame.mixer.Sound(buffer=np.repeat(raw_samples, 2).tobytes())

        # Set channel volume to 0 before playing to prevent a brief burst at
        # the default volume (1.0) before the ramp thread starts.
        _channels[channel].set_volume(0, 0)
        _channels[channel].play(sound, loops=loops)

        # Ramp from 0 to the desired volume for a smooth start.
        # Use target_volumes (from Player, which tracks the user's intended volume)
        # rather than _volumes (which may hold an intermediate ramp value after a stop).
        channel_volume = target_volumes[channel] if target_volumes else _volumes[channel]
        ramp_volume(volume_start=0, volume_end=channel_volume, channel=channel)

    _clock_time = time.time()
    _audio_time = audio_time


def ramp_volume(volume_end: float, volume_start: float = None, channel: int = None, ramp_length: float = None):
    """Smoothly ramp a channel's volume in a daemon thread.

    :param volume_end: Target volume (0-100).
    :param volume_start: Starting volume (defaults to current channel volume).
    :param channel: Channel index, or None to ramp all channels.
    :param ramp_length: Duration in seconds (auto-calculated from volume delta if None).
    """
    global _channels, _volumes, _volume_thread_times

    if channel is None:
        for i_channel, _ in enumerate(_channels):
            ramp_volume(
                volume_end=volume_end,
                volume_start=volume_start,
                channel=i_channel,
                ramp_length=ramp_length)
        return

    # Starting volume will be the current volume of the channel if not defined
    volume_start = volume_start if volume_start is not None else _volumes[channel]

    # Ensure volumes are constrained from 0 to 100
    volume_start = max(0, min(100, volume_start))
    volume_end = max(0, min(100, volume_end))

    # Calculate the ramp length (in seconds) based on how large of a change in volume we are making
    ramp_length = ramp_length if ramp_length is not None else es.cfg['player.volume-ramp-min-length'] + abs(
        (es.cfg['player.volume-ramp-max-length'] - es.cfg['player.volume-ramp-min-length']) *
        (volume_end - volume_start) / 100)
    step_length = 0.02

    # Calculate the number of steps to ramp the volume (at least 1 to ensure the final volume is applied)
    volume_steps = max(1, round(ramp_length / step_length))

    # Set the start time of this thread (used to allow the thread exit early if another is started before it finishes)
    _volume_thread_times[channel] = time.time()

    def ramp_volume_thread():
        global _channels, _volumes, _volume_thread_times

        thread_start_time = time.time()
        _volumes[channel] = volume_start

        for current_volume in np.linspace(volume_start, volume_end, volume_steps):
            # See if this thread should exit because another more recent
            # thread controlling the volume of this channel has been started
            if not _is_playing or _volume_thread_times[channel] > thread_start_time:
                return

            # Set the current volume
            _set_channel_volume_unsafe(volume=current_volume, channel=channel)
            _volumes[channel] = current_volume

            # Sleep before starting the next iteration
            time.sleep(step_length)

    thread = threading.Thread(target=ramp_volume_thread)
    thread.daemon = True
    thread.start()


def set_volume(volume: float = None, channel: int = None):
    """Set volume for a channel with an appropriate ramp (short for decrease, longer for increase)."""
    global _channels, _volumes, _volume_thread_times

    if channel is None:
        for i_channel, _ in enumerate(_channels):
            set_volume(channel=i_channel, volume=volume)
        return

    volume = volume if volume is not None else _volumes[channel]

    if volume < _volumes[channel]:
        # Decreasing: short ramp to avoid audible click from abrupt volume drop
        ramp_volume(volume_end=volume, channel=channel, ramp_length=0.15)
    elif volume > _volumes[channel]:
        # Increasing: longer ramp to avoid sudden jolt
        ramp_volume(volume_end=volume, channel=channel)


def stop():
    """Stop playback with a synchronous fade-to-zero to prevent audio pops."""
    global _is_playing, _audio_time, _clock_time

    if not _is_playing:
        return

    # Set _is_playing to False first so that any running ramp threads exit
    # on their next iteration (their _set_channel_volume_unsafe calls also
    # become no-ops). Update timestamps as a secondary signal.
    _is_playing = False
    for i in range(len(_volume_thread_times)):
        _volume_thread_times[i] = time.time()

    # Synchronous fade-to-zero to prevent pops. Uses direct channel.set_volume()
    # calls with proper L/R stereo panning, avoiding SDL_mixer's fadeout() which
    # only updates volume at buffer boundaries and produces zipper noise.
    # With buffer=256 at 44100Hz, each buffer is ~5.8ms. We call set_volume
    # every 3ms (faster than the buffer period) so that each buffer fill picks
    # up the most recent value. Over 90ms this yields ~15 effective volume
    # steps of ~6-7% each — small enough to be inaudible.
    if _channels and any(ch.get_busy() for ch in _channels):
        fade_steps = 30
        step_sleep = 0.003
        for step in range(fade_steps - 1, -1, -1):
            scale = step / fade_steps
            for i, ch in enumerate(_channels):
                vol = (_volumes[i] / 100) * _ramp_gain * scale
                if len(_channels) == 1:
                    ch.set_volume(vol, vol)
                elif i % 2 == 0:
                    ch.set_volume(vol, 0)
                else:
                    ch.set_volume(0, vol)
            time.sleep(step_sleep)
        # Hold at zero for one buffer period to ensure silence reaches the
        # audio output before channels are stopped.
        time.sleep(0.008)

    for channel in _channels:
        channel.stop()

    _audio_time = 0
    _clock_time = 0

    pygame.mixer.quit()



def _get_repeat_mode() -> str:
    """Get the current repeat mode ('none', 'one', or 'all')."""
    return str(es.cfg['player.repeat'])


def _set_channel_volume_unsafe(volume: float = None, channel: int = None):
    """Set a pygame channel's stereo volume directly, with no ramp or thread safety.

    Called from ramp threads. No-op if playback has stopped or channel is invalid.
    """
    global _channels

    if _is_playing and _channels and -len(_channels) <= channel < len(_channels):
        vol = volume / 100 * _ramp_gain
        if len(_channels) == 1:
            _channels[channel].set_volume(vol, vol)
        elif channel % 2 == 0:
            _channels[channel].set_volume(vol, 0)
        else:
            _channels[channel].set_volume(0, vol)
