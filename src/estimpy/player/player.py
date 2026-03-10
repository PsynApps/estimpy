"""Interactive player for estim audio files.

Manages playback state (play/pause/stop/seek), volume and mute per channel,
playlist navigation, and the Qt player window lifecycle.
"""
import typing

import estimpy as es


class Player:
    """Coordinates audio playback, visualization, and UI for a playlist of audio files.

    :param audio_files: List of file paths to play.
    """

    def __init__(self, audio_files: list):
        self._current_file = 0
        self._audio_files = audio_files
        self._es_audio = None
        self._window = None

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

        # Lazy import to avoid circular dependency (player is imported before visualization in __init__.py)
        from estimpy.player.window import PlayerWindow
        self._window = PlayerWindow(player=self, es_audio=self._es_audio)

    def get_audio_files(self) -> list:
        """Return the playlist file paths."""
        return self._audio_files

    def get_channel_volume(self, channel) -> float:
        """Return the target volume (0-100) for a channel, or None if out of range."""
        if channel < self._es_audio.channels:
            return self._channel_volumes[channel]

    def get_current_file_index(self) -> int:
        """Return the index of the currently loaded file in the playlist."""
        return self._current_file

    def get_es_audio(self) -> es.audio.Audio:
        """Return the currently loaded Audio object."""
        return self._es_audio

    def get_repeat_mode(self) -> str:
        """Get the current repeat mode ('none', 'one', or 'all')."""
        return str(es.cfg['player.repeat'])

    def get_time(self) -> float:
        """Return current playback position in seconds."""
        return es.player.audio.get_time() if self._playing else self._time

    def is_channel_muted(self, channel) -> bool:
        """Return True if the given channel is muted, or None if out of range."""
        if channel < self._es_audio.channels:
            return self._channel_muted[channel]

    def is_full_screen(self) -> bool:
        """Return True if the player window is in fullscreen mode."""
        return self._full_screen

    def is_master_muted(self) -> bool:
        """Return True if master mute is active."""
        return self._master_muted

    def is_playing(self) -> bool:
        """Return True if audio is currently playing."""
        return self._playing

    def mute(self, channel: int = None) -> None:
        """Mute a channel, or all channels if channel is None (master mute)."""
        if channel is None:
            # Mute master, set volume to all channels to 0 but don't update their individual UI
            for channel_id in range(self._es_audio.channels):
                es.player.audio.set_volume(volume=0, channel=channel_id)
            self._master_muted = True
        else:
            # Mute channel
            es.player.audio.set_volume(volume=0, channel=channel)
            self._channel_muted[channel] = True

        if self._window:
            self._window.mute(channel)

    def on_track_finished(self) -> None:
        """Handle end-of-track based on repeat mode and playlist position."""
        repeat_mode = self.get_repeat_mode()

        if repeat_mode == 'one':
            # Audio handles looping internally (loops=-1), so this shouldn't
            # normally trigger. Handle it as a safety fallback.
            self.play()
        elif repeat_mode == 'all':
            # Advance to next file, wrapping around to the start
            if self._current_file is not None and len(self._audio_files) > 0:
                next_idx = (self._current_file + 1) % len(self._audio_files)
                self.set_audio(file_index=next_idx)
            else:
                self.stop()
        else:  # 'none'
            # Advance to next file if available, otherwise stop
            if self._current_file is not None and self._current_file < len(self._audio_files) - 1:
                self.set_audio(file_index=self._current_file + 1)
            else:
                self.stop()

    def pause(self) -> None:
        """Pause playback, saving the current position for later resume."""
        self._time = self.get_time()
        self._playing = False

        # Update UI immediately (before the blocking audio fade)
        if self._window:
            self._window.pause()

        es.player.audio.stop()

    def play(self) -> None:
        """Start or resume playback from the saved position."""
        self._playing = True

        # If trying to play from the end of the file, reset to the beginning
        if self._time >= self._es_audio.length:
            self._time = 0

        # Pass current channel volumes so audio.play() uses the correct ramp
        # targets (not the intermediate ramp values that _volumes may contain
        # after a stop/seek cycle).
        target_volumes = []
        for ch in range(self._es_audio.channels):
            if self._master_muted or self._channel_muted[ch]:
                target_volumes.append(0)
            else:
                target_volumes.append(self._channel_volumes[ch])

        es.player.audio.play(audio_time=self._time, target_volumes=target_volumes)

        if self._window:
            self._window.play()

    def previous_file(self) -> None:
        """Load the previous file in the playlist, if any."""
        if self._current_file is not None and self._current_file > 0:
            self.set_audio(file_index=self._current_file - 1)

    def next_file(self) -> None:
        """Load the next file in the playlist, if any."""
        if self._current_file is not None and self._current_file < len(self._audio_files) - 1:
            self.set_audio(file_index=self._current_file + 1)

    def add_files(self, file_paths: list) -> None:
        """Append files to the end of the playlist."""
        self._audio_files.extend(file_paths)
        if self._window:
            self._window.update_playlist()

    def remove_file(self, index: int) -> bool:
        """Remove a file from the playlist. Returns False if index is the current file or invalid."""
        if index == self._current_file:
            return False
        if index < 0 or index >= len(self._audio_files):
            return False

        self._audio_files.pop(index)

        if index < self._current_file:
            self._current_file -= 1

        if self._window:
            self._window.update_playlist()

        return True

    def reorder_file(self, from_index: int, to_index: int) -> None:
        """Move a file within the playlist, adjusting the current file index accordingly."""
        if from_index == to_index:
            return
        if from_index < 0 or from_index >= len(self._audio_files):
            return
        if to_index < 0 or to_index >= len(self._audio_files):
            return

        file_path = self._audio_files.pop(from_index)
        self._audio_files.insert(to_index, file_path)

        # Adjust _current_file to track the currently playing file
        if from_index == self._current_file:
            self._current_file = to_index
        elif from_index < self._current_file <= to_index:
            self._current_file -= 1
        elif to_index <= self._current_file < from_index:
            self._current_file += 1

    def load_playlist(self, file_paths: list) -> None:
        """Replace the playlist and load the first file."""
        if not file_paths:
            return

        self._audio_files = list(file_paths)
        self._current_file = 0
        self.set_audio(file_index=0)

        if self._window:
            self._window.update_playlist()

    def set_audio(self, es_audio: es.audio.Audio = None, file_index: int = None) -> None:
        """Load a new audio source, either from an Audio object or a playlist index."""
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

        # Resize channel state lists if the channel count changed
        new_channels = self._es_audio.channels
        old_channels = len(self._channel_volumes)
        if new_channels > old_channels:
            self._channel_volumes.extend([es.cfg['player.volume-start']] * (new_channels - old_channels))
            self._channel_muted.extend([False] * (new_channels - old_channels))
        elif new_channels < old_channels:
            self._channel_volumes = self._channel_volumes[:new_channels]
            self._channel_muted = self._channel_muted[:new_channels]

        es.player.audio.load(es_audio=self._es_audio)
        if self._window:
            self._window.load(es_audio=self._es_audio)

        if was_playing:
            self.play()

    def set_time(self, time: float) -> None:
        """Seek to a position in seconds, clamped to [0, length]. Restarts playback if playing."""
        was_playing = self._playing

        if was_playing:
            self.stop()

        self._time = max(0, min(time, self._es_audio.length))
        if self._window:
            self._window.set_time(time)

        if was_playing:
            self.play()

    def set_volume(self, volume: int, channel: int = None) -> None:
        """Set volume (0-100) for a channel, or all channels if channel is None.

        Respects mute state — muted channels are not sent to the audio backend.
        """
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
        """Show the player window."""
        if self._window:
            self._window.show_window()

    def stop(self):
        """Stop playback and reset position to the beginning."""
        self._playing = False

        # Update UI immediately (before the blocking audio fade)
        if self._window:
            self._window.stop()

        es.player.audio.stop()
        self.set_time(0)

    def step_volume(self, volume_step: int, channel: int = None):
        """Adjust volume by a relative step, for a channel or all channels."""
        if channel is None:
            for channel_id in range(self._es_audio.channels):
                self.step_volume(volume_step=volume_step, channel=channel_id)
            return

        self.set_volume(volume=self.get_channel_volume(channel) + volume_step, channel=channel)

    def toggle_full_screen(self):
        """Toggle between fullscreen and windowed display."""
        if self.is_full_screen():
            self._full_screen = False
        else:
            self._full_screen = True

        if self._window:
            self._window.toggle_full_screen()

    def toggle_muted(self, channel: int = None):
        """Toggle mute for a channel, or master mute if channel is None."""
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
        """Toggle between playing and paused states."""
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def unmute(self, channel: int = None):
        """Unmute a channel, or all channels if channel is None (master unmute).

        Channel unmute respects master mute — audio volume is not restored until
        master is also unmuted. Master unmute respects individual channel mutes.
        """
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

        if self._window:
            self._window.unmute(channel)
