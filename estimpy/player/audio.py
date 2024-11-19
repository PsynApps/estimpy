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


def get_time() -> float:
    global _audio_time, _clock_time

    if is_playing():
        # get_pos() returns milliseconds
        audio_time_current = _audio_time + time.time() - _clock_time
        # Taking the modulus of the position with the length allows us to support looping
        return audio_time_current % _es_audio.length
    else:
        return 0


def get_volume(channel: int) -> float:
    return _volumes[channel]


def get_volumes() -> typing.List[float]:
    return _volumes.copy()


def initialize() -> None:
    global _volumes, _volume_thread_times

    max_channels = 2

    _volumes = [es.cfg['player.volume-start']] * max_channels
    _volume_thread_times = [0] * max_channels


def is_paused() -> bool:
    return not _is_playing and _clock_time > 0


def is_playing() -> bool:
    return _is_playing # and _audio_time + time.time() - _clock_time <= _es_audio.length


def load(es_audio: es.audio.Audio):
    global _es_audio, _initialized

    if not _initialized:
        initialize()
        _initialized = True

    _es_audio = es_audio


def pause_unpause():
    global _is_playing, _audio_time, _clock_time

    if is_playing():
        for channel in _channels:
            channel.pause()

        _is_playing = False
    elif _channels:
        for channel in _channels:
            channel.unpause()

        _audio_time = get_time()
        _clock_time = time.time()
        _is_playing = True


def play(audio_time: float = 0):
    global _is_playing, _audio_time, _clock_time, _channels, _volumes

    if is_playing():
        # Should only happen if audio_time is different
        stop()
    elif is_paused():
        pause_unpause()
        return

    sample_time = _es_audio.time_to_data_index(audio_time)

    pygame.mixer.init(frequency=_es_audio.sample_rate, size=-_es_audio.bit_depth, channels=2)

    loops = -1 if es.cfg['player.repeat'] else 0

    _channels = []

    # _is_playing must be set to true so that the set_volume() calls for each channel work correctly
    _is_playing = True

    # Prepare Sound objects
    for channel in range(_es_audio.channels):
        _channels.append(pygame.mixer.Channel(channel))

        # Even though we are playing through just one channel, Sound() buffer expects interleaved stereo audio
        # data, so we have to duplicate every sample.
        sound = pygame.mixer.Sound(buffer=np.repeat(_es_audio.data_raw[channel, sample_time:], 2).tobytes())

        # Having a very short fade should ensure the volume is at or near 0
        # until the volume can be explicitly set to 0
        _channels[channel].play(sound, loops=loops, fade_ms=100)

        # Set channel volume to 0, then call set_volume() again to the correct volume.
        # This will make playback start from 0 and ramp up to the desired volume.
        channel_volume = _volumes[channel]
        ramp_volume(volume_start=0, volume_end=channel_volume, channel=channel)

    _clock_time = time.time()
    _audio_time = audio_time


def ramp_volume(volume_end: float, volume_start: float = None, channel: int = None, ramp_length: float = None):
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
    step_length = 0.1

    # Calculate the number of steps to ramp the volume
    volume_steps = round(ramp_length / step_length)

    # Set the start time of this thread (used to allow the thread exit early if another is started before it finishes)
    _volume_thread_times[channel] = time.time()

    def ramp_volume_thread():
        global _channels, _volumes, _volume_thread_times

        thread_start_time = time.time()
        _volumes[channel] = volume_start

        for current_volume in np.linspace(volume_start, volume_end, volume_steps):
            # See if this thread should exit because another more recent
            # thread controlling the volume of this channel has been started
            if not is_playing() or _volume_thread_times[channel] > thread_start_time:
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
    global _channels, _volumes

    if channel is None:
        for i_channel, _ in enumerate(_channels):
            set_volume(channel=i_channel, volume=volume)
        return

    volume = volume if volume is not None else _volumes[channel]

    if volume <= _volumes[channel]:
        # Decreasing volume can happen instantaneously
        _set_channel_volume_unsafe(volume=volume, channel=channel)
        _volumes[channel] = volume
    else:
        # Increasing volume should be ramped to avoid sudden jolts
        ramp_volume(volume_end=volume, channel=channel)


def stop():
    global _is_playing, _audio_time, _clock_time

    if is_playing():
        for channel in _channels:
            channel.stop()

        _is_playing = False
        _audio_time = 0
        _clock_time = 0

        pygame.mixer.quit()


def toggle_playing():
    if is_playing() or is_paused():
        pause_unpause()
    else:
        play()


def _set_channel_volume_unsafe(volume: float = None, channel: int = None):
    global _channels

    if is_playing() and -len(_channels) <= channel < len(_channels):
        if len(_channels) == 1:
            _channels[channel].set_volume(volume / 100, volume / 100)
        elif channel % 2 == 0:
            _channels[channel].set_volume(volume / 100, 0)
        else:
            _channels[channel].set_volume(0, volume / 100)