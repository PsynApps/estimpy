"""A module to render an interactive player for estim audio files"""
import typing

import estimpy as es


class Player:
    def __init__(self, audio_files: list, width: int = None, height: int = None):
        self._current_file = 0
        self._audio_files = audio_files
        self._es_audio = None
        self._visualization = None

        if not self._audio_files:
            return

        # Estim audio of current file
        self._es_audio = es.audio.Audio(file=self._audio_files[self._current_file]) #  type: es.audio.Audio

        self._channel_muted = [False] * self._es_audio.channels  # type: typing.List[bool]
        self._channel_volumes = [es.cfg['player.volume-start']] * self._es_audio.channels  # type: typing.List[float]
        self._master_muted = False  # type: bool
        self._playing = False  # type: bool
        self._full_screen = False  # type: bool
        self._time = 0  # type: float

        es.player.audio.load(self._es_audio)

        width = es.cfg['visualization.video.display.width'] if width is None else width
        height = es.cfg['visualization.video.display.height'] if height is None else height

        self._visualization = es.visualization.VideoPlayerVisualization(player=self)
        self._visualization.make_figure()
        self._visualization.resize_figure(width=width, height=height)

    def get_channel_volume(self, channel) -> float:
        if channel < self._es_audio.channels:
            return self._channel_volumes[channel]

    def get_es_audio(self) -> es.audio.Audio:
        return self._es_audio

    def get_time(self) -> float:
        return es.player.audio.get_time() if self._playing else self._time

    def is_channel_muted(self, channel) -> bool:
        if channel < self._es_audio.channels:
            return self._channel_muted[channel]

    def is_full_screen(self) -> bool:
        return self._full_screen

    def is_master_muted(self) -> bool:
        return self._master_muted

    def is_playing(self) -> bool:
        return self._playing

    def mute(self, channel: int = None) -> None:
        if channel is None:
            # Mute master, set volume to all channels to 0 but don't update their individual UI
            for channel_id in range(self._es_audio.channels):
                es.player.audio.set_volume(volume=0, channel=channel_id)
            self._master_muted = True
        else:
            # Mute channel
            es.player.audio.set_volume(volume=0, channel=channel)
            self._channel_muted[channel] = True

        if self._visualization:
            self._visualization.mute(channel)

    def pause(self) -> None:
        self._time = self.get_time()
        self._playing = False

        es.player.audio.stop()

        if self._visualization:
            self._visualization.pause()

    def play(self) -> None:
        self._playing = True

        # If trying to play from the end of the file, reset to the beginning
        if self._time >= self._es_audio.length:
            self._time = 0

        es.player.audio.play(audio_time=self._time)

        if self._visualization:
            self._visualization.play()

    def previous_file(self) -> None:
        if self._current_file is not None and self._current_file > 0:
            self.set_audio(file_index=self._current_file - 1)

    def next_file(self) -> None:
        if self._current_file is not None and self._current_file < len(self._audio_files) - 1:
            self.set_audio(file_index=self._current_file + 1)

    def set_audio(self, es_audio: es.audio.Audio = None, file_index: int = None) -> None:
        was_playing = self.is_playing()

        self.stop()

        if es_audio:
            self._es_audio = es_audio
            self._current_file = None
        elif -len(self._audio_files) <= file_index < len(self._audio_files):
            es_audio = es.audio.Audio(file=self._audio_files[file_index])
            if es_audio:
                self._es_audio = es_audio
                self._current_file = file_index

        es.player.audio.load(es_audio=self._es_audio)
        self._visualization.load(es_audio=self._es_audio)

        if was_playing:
            self.play()

    def set_time(self, time: float) -> None:
        was_playing = self._playing

        if was_playing:
            self.stop()

        self._time = time
        if self._visualization:
            self._visualization.set_time(time)

        if was_playing:
            self.play()

    def set_volume(self, volume: int, channel: int = None) -> None:
        if channel is None:
            for channel_id in range(self._es_audio.channels):
                self.set_volume(volume=volume, channel=channel_id)
            return

        volume = volume if volume is not None else self.get_channel_volume(channel)

        self._channel_volumes[channel] = max(0, min(100, round(volume)))

        # Don't override mute(s)
        if not self._master_muted and not self._channel_muted[channel]:
            es.player.audio.set_volume(volume=self.get_channel_volume(channel), channel=channel)

    def show(self):
        if self._visualization:
            self._visualization.show_figure()

    def stop(self):
        self._playing = False

        es.player.audio.stop()
        self.set_time(0)

        if self._visualization:
            self._visualization.stop()

    def step_volume(self, volume_step: int, channel: int = None):
        if channel is None:
            for channel_id in range(self._es_audio.channels):
                self.step_volume(volume_step=volume_step, channel=channel_id)
            return

        self.set_volume(volume=self.get_channel_volume(channel) + volume_step, channel=channel)

    def toggle_full_screen(self):
        if self.is_full_screen():
            self._full_screen = False
        else:
            self._full_screen = True

        if self._visualization:
            self._visualization.toggle_full_screen()

    def toggle_muted(self, channel: int = None):
        if channel is None:
            if self._master_muted:
                self.unmute()
            else:
                self.mute()
        else:
            if self.is_channel_muted(channel):
                self.unmute(channel=channel)
            else:
                self.mute(channel=channel)

    def toggle_playing(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def unmute(self, channel: int = None):
        if channel is None:
            # Unmute master, set volume to all channels to 0 but don't update their individual UI
            for channel_id in range(self._es_audio.channels):
                # Don't override a channel mute
                if not self.is_channel_muted(channel_id):
                    es.player.audio.set_volume(volume=self.get_channel_volume(channel_id), channel=channel_id)
            self._master_muted = False
        else:
            # Unmute channel
            if not self.is_master_muted():
                # Don't override master mute
                es.player.audio.set_volume(volume=self.get_channel_volume(channel), channel=channel)
            self._channel_muted[channel] = False

        if self._visualization:
            self._visualization.unmute(channel)