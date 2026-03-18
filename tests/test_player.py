"""Tests for Player pure-logic methods (no Qt or pygame required)."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import estimpy as es
from estimpy.audio import Audio


SAMPLE_RATE = 44100
N_SAMPLES = 44100  # 1 second


def _make_stereo_audio():
    """Create a minimal stereo Audio for testing."""
    data = np.zeros((2, N_SAMPLES), dtype=np.int16)
    return Audio(audio_data=data, sample_rate=SAMPLE_RATE, bit_depth=16)


@pytest.fixture
def player():
    """Create a Player with 3 dummy files, mocking the window and audio backend."""
    with patch('estimpy.player.window.PlayerWindow'), \
         patch('estimpy.player.audio.load'), \
         patch('estimpy.player.audio.play'), \
         patch('estimpy.player.audio.stop'), \
         patch('estimpy.player.audio.set_volume'), \
         patch('estimpy.player.audio.get_time', return_value=0.0), \
         patch('estimpy.audio.Audio', return_value=_make_stereo_audio()):
        p = es.player.player.Player(audio_files=['/fake/a.mp3', '/fake/b.mp3', '/fake/c.mp3'])
        # Replace the window with a simple mock so method calls don't error
        p._window = MagicMock()
        yield p


class TestRemoveFile:
    def test_remove_after_current(self, player):
        assert player.remove_file(2) is True
        assert player.get_audio_files() == ['/fake/a.mp3', '/fake/b.mp3']
        assert player.get_current_file_index() == 0

    def test_remove_before_current(self, player):
        """Removing a file before current should decrement current index."""
        player._current_file = 2
        assert player.remove_file(0) is True
        assert player.get_audio_files() == ['/fake/b.mp3', '/fake/c.mp3']
        assert player.get_current_file_index() == 1

    def test_remove_current_file_rejected(self, player):
        assert player.remove_file(0) is False
        assert len(player.get_audio_files()) == 3

    def test_remove_invalid_index(self, player):
        assert player.remove_file(5) is False
        assert player.remove_file(-1) is False

    def test_remove_last_non_current(self, player):
        """Remove the only non-current file."""
        player._audio_files = ['/fake/a.mp3', '/fake/b.mp3']
        player._current_file = 0
        assert player.remove_file(1) is True
        assert player.get_audio_files() == ['/fake/a.mp3']


class TestReorderFile:
    def test_move_forward(self, player):
        """Move file 0 to position 2."""
        player._current_file = 0
        player.reorder_file(0, 2)
        assert player.get_audio_files() == ['/fake/b.mp3', '/fake/c.mp3', '/fake/a.mp3']
        assert player.get_current_file_index() == 2

    def test_move_backward(self, player):
        """Move file 2 to position 0."""
        player._current_file = 2
        player.reorder_file(2, 0)
        assert player.get_audio_files() == ['/fake/c.mp3', '/fake/a.mp3', '/fake/b.mp3']
        assert player.get_current_file_index() == 0

    def test_current_between_forward(self, player):
        """Current file is between from and to (moving forward past it)."""
        player._current_file = 1
        player.reorder_file(0, 2)
        assert player.get_current_file_index() == 0

    def test_current_between_backward(self, player):
        """Current file is between to and from (moving backward past it)."""
        player._current_file = 1
        player.reorder_file(2, 0)
        assert player.get_current_file_index() == 2

    def test_noop_same_index(self, player):
        player._current_file = 0
        player.reorder_file(1, 1)
        assert player.get_audio_files() == ['/fake/a.mp3', '/fake/b.mp3', '/fake/c.mp3']

    def test_invalid_indices(self, player):
        player.reorder_file(-1, 0)
        player.reorder_file(0, 5)
        assert player.get_audio_files() == ['/fake/a.mp3', '/fake/b.mp3', '/fake/c.mp3']

    def test_current_unaffected_when_outside_range(self, player):
        """Moving files that don't straddle current should not change it."""
        player._current_file = 0
        player.reorder_file(1, 2)
        assert player.get_current_file_index() == 0


class TestOnTrackFinished:
    def test_repeat_none_advances(self, player):
        player._current_file = 0
        with patch.object(player, 'set_audio') as mock_set:
            player.on_track_finished()
            mock_set.assert_called_once_with(file_index=1)

    def test_repeat_none_stops_at_end(self, player):
        player._current_file = 2  # last file
        with patch.object(player, 'stop') as mock_stop:
            player.on_track_finished()
            mock_stop.assert_called_once()

    def test_repeat_one_plays(self, player):
        es.cfg['player.repeat'] = 'one'
        with patch.object(player, 'play') as mock_play:
            player.on_track_finished()
            mock_play.assert_called_once()

    def test_repeat_all_wraps(self, player):
        player._current_file = 2  # last file
        es.cfg['player.repeat'] = 'all'
        with patch.object(player, 'set_audio') as mock_set:
            player.on_track_finished()
            mock_set.assert_called_once_with(file_index=0)

    def test_repeat_all_advances(self, player):
        player._current_file = 0
        es.cfg['player.repeat'] = 'all'
        with patch.object(player, 'set_audio') as mock_set:
            player.on_track_finished()
            mock_set.assert_called_once_with(file_index=1)


class TestSetVolume:
    def test_clamps_to_range(self, player):
        player.set_volume(150, channel=0)
        assert player.get_channel_volume(0) == 100

        player.set_volume(-10, channel=0)
        assert player.get_channel_volume(0) == 0

    def test_sets_all_channels(self, player):
        player.set_volume(75)
        assert player.get_channel_volume(0) == 75
        assert player.get_channel_volume(1) == 75

    def test_respects_mute(self, player):
        """Muted channel should not send volume to audio backend."""
        player._channel_muted[0] = True
        with patch('estimpy.player.audio.set_volume') as mock_sv:
            player.set_volume(60, channel=0)
            mock_sv.assert_not_called()
        assert player.get_channel_volume(0) == 60


class TestGetChannelVolume:
    def test_valid_channel(self, player):
        player._channel_volumes[0] = 42
        assert player.get_channel_volume(0) == 42

    def test_out_of_range(self, player):
        assert player.get_channel_volume(99) == 0


class TestIsChannelMuted:
    def test_valid_channel(self, player):
        player._channel_muted[1] = True
        assert player.is_channel_muted(1) is True
        assert player.is_channel_muted(0) is False

    def test_out_of_range(self, player):
        assert player.is_channel_muted(99) is False


class TestMuteUnmute:
    def test_master_mute_unmute(self, player):
        player.mute()
        assert player.is_master_muted() is True

        player.unmute()
        assert player.is_master_muted() is False

    def test_channel_mute_unmute(self, player):
        player.mute(channel=0)
        assert player.is_channel_muted(0) is True

        player.unmute(channel=0)
        assert player.is_channel_muted(0) is False

    def test_toggle_muted(self, player):
        player.toggle_muted(channel=1)
        assert player.is_channel_muted(1) is True

        player.toggle_muted(channel=1)
        assert player.is_channel_muted(1) is False

    def test_channel_unmute_respects_master(self, player):
        """Unmuting a channel while master is muted should not restore audio volume."""
        player.mute()  # master mute
        player.mute(channel=0)

        with patch('estimpy.player.audio.set_volume') as mock_sv:
            player.unmute(channel=0)
            mock_sv.assert_not_called()
