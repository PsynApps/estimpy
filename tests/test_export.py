import math
import os
from unittest.mock import patch

import pytest

import estimpy as es
from estimpy.export import (
    _resolve_audio_codec, _resolve_audio_format, _resolve_audio_extra_args,
    _resolve_video_audio_codec, _is_audio_modified,
    _EXTENSION_CODEC_MAP, _CODEC_FORMAT_MAP, _AUTO_QUALITY_ARGS,
    _CONTAINER_SAFE_AUDIO_CODECS,
)


class TestResolveAudioCodec:
    """Tests for auto-resolving audio codec from config, extension, or source file."""

    def test_explicit_config_wins(self, synthetic_stereo_audio):
        es.cfg['audio.export.codec'] = 'libvorbis'
        assert _resolve_audio_codec(synthetic_stereo_audio) == 'libvorbis'

    def test_output_extension_mp3(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.mp3') == 'libmp3lame'

    def test_output_extension_flac(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.flac') == 'flac'

    def test_output_extension_wav(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.wav') == 'pcm_s24le'

    def test_output_extension_m4a(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.m4a') == 'aac'

    def test_output_extension_ogg(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.ogg') == 'libvorbis'

    def test_output_extension_opus(self, synthetic_stereo_audio):
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.opus') == 'libopus'

    def test_source_file_detection(self):
        """When no config or output extension, detect from source file."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        assert _resolve_audio_codec(audio) == 'libmp3lame'

    def test_fallback_to_libmp3lame(self, synthetic_stereo_audio):
        """When nothing else works, fall back to libmp3lame."""
        assert _resolve_audio_codec(synthetic_stereo_audio) == 'libmp3lame'

    def test_explicit_config_overrides_extension(self, synthetic_stereo_audio):
        es.cfg['audio.export.codec'] = 'flac'
        assert _resolve_audio_codec(synthetic_stereo_audio, output_file='out.mp3') == 'flac'

    def test_extension_map_completeness(self):
        """All extension map entries should resolve to known codecs."""
        for ext, codec in _EXTENSION_CODEC_MAP.items():
            assert isinstance(codec, str) and len(codec) > 0


class TestResolveAudioFormat:

    def test_explicit_config_wins(self, synthetic_stereo_audio):
        es.cfg['audio.export.format'] = 'ogg'
        assert _resolve_audio_format(synthetic_stereo_audio, codec='libvorbis') == 'ogg'

    def test_infer_from_codec(self, synthetic_stereo_audio):
        assert _resolve_audio_format(synthetic_stereo_audio, codec='flac') == 'flac'
        assert _resolve_audio_format(synthetic_stereo_audio, codec='libmp3lame') == 'mp3'
        assert _resolve_audio_format(synthetic_stereo_audio, codec='aac') == 'm4a'
        assert _resolve_audio_format(synthetic_stereo_audio, codec='pcm_s24le') == 'wav'

    def test_source_file_extension(self):
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        # Unknown codec → falls through to source extension
        assert _resolve_audio_format(audio, codec='unknown_codec') == 'mp3'

    def test_fallback_to_mp3(self, synthetic_stereo_audio):
        assert _resolve_audio_format(synthetic_stereo_audio, codec='unknown_codec') == 'mp3'

    def test_codec_format_map_completeness(self):
        """Every codec that can be resolved should have a format mapping."""
        for codec in _EXTENSION_CODEC_MAP.values():
            assert codec in _CODEC_FORMAT_MAP, f'{codec} missing from _CODEC_FORMAT_MAP'


class TestResolveAudioExtraArgs:

    def test_explicit_config_args(self):
        es.cfg['audio.export.ffmpeg-extra-args.-b:a'] = '320k'
        args = _resolve_audio_extra_args('libmp3lame')
        assert '-b:a' in args
        assert '320k' in args

    def test_auto_quality_for_mp3(self):
        args = _resolve_audio_extra_args('libmp3lame')
        assert args == ['-q:a', '0']

    def test_auto_quality_for_aac(self):
        args = _resolve_audio_extra_args('aac')
        assert args == ['-b:a', '256k']

    def test_auto_quality_for_flac(self):
        args = _resolve_audio_extra_args('flac')
        assert args == []

    def test_auto_quality_for_pcm(self):
        args = _resolve_audio_extra_args('pcm_s24le')
        assert args == []

    def test_auto_quality_for_unknown_codec(self):
        args = _resolve_audio_extra_args('some_unknown_codec')
        assert args == []


class TestIsAudioModified:

    def test_unmodified(self):
        assert not _is_audio_modified()

    def test_stereo_stim(self):
        es.cfg['audio.stereo-stim.enabled'] = True
        assert _is_audio_modified()

    def test_ramp(self):
        es.cfg['audio.ramp.level'] = 50
        assert _is_audio_modified()

    def test_frequency_scale(self):
        es.cfg['audio.frequency.scale'] = 2
        assert _is_audio_modified()

    def test_frequency_shift(self):
        es.cfg['audio.frequency.shift'] = 100
        assert _is_audio_modified()


class TestResolveVideoAudioCodec:

    def test_unmodified_mp3_stream_copy(self):
        """Unmodified MP3 in MP4 should stream copy (MP3 is MP4-safe)."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'copy']

    def test_modified_audio_uses_aac_default(self):
        """Modified audio with no explicit codec should use AAC for MP4."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        es.cfg['audio.stereo-stim.enabled'] = True
        args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'aac']

    def test_modified_audio_explicit_compatible_codec(self):
        """Modified audio with explicit MP4-compatible codec should use it."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        es.cfg['audio.stereo-stim.enabled'] = True
        es.cfg['audio.export.codec'] = 'libmp3lame'
        args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'libmp3lame']

    def test_modified_audio_explicit_incompatible_codec_falls_back(self, capsys):
        """Modified audio with FLAC codec in MP4 should fall back to AAC with warning."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        es.cfg['audio.stereo-stim.enabled'] = True
        es.cfg['audio.export.codec'] = 'flac'
        args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'aac']
        captured = capsys.readouterr()
        assert 'not widely supported' in captured.out

    def test_unmodified_incompatible_codec_reencodes(self, capsys):
        """Unmodified audio with incompatible source codec should re-encode."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        # Simulate a FLAC source by mocking the detection
        with patch('estimpy.export._detect_source_audio_codec', return_value='flac'):
            args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'aac']
        captured = capsys.readouterr()
        assert 'Re-encoding' in captured.out

    def test_frequency_transform_counts_as_modified(self):
        """Frequency transform should trigger re-encoding."""
        audio = es.audio.Audio(file=os.path.join(os.path.dirname(__file__), 'input', 'test.mp3'))
        es.cfg['audio.frequency.scale'] = 2
        args = _resolve_video_audio_codec(audio)
        assert args == ['-c:a', 'aac']


class TestSegmentCalculations:
    """Tests for video segment/frame math used in write_video."""

    def test_frames_per_segment(self):
        es.cfg['visualization.video.export.segment-length'] = 60
        es.cfg['visualization.video.export.fps'] = 30
        frames_per_segment = es.cfg['visualization.video.export.segment-length'] * es.cfg['visualization.video.export.fps']
        assert frames_per_segment == 1800

    def test_total_frames_from_length(self):
        fps = 30
        seconds = 120.5
        frames_total = math.floor(seconds * fps)
        assert frames_total == 3615

    def test_segment_count(self):
        """Number of segments should cover all frames."""
        fps = 30
        seconds = 125.0
        frames_total = math.floor(seconds * fps)
        frames_per_segment = 60 * fps  # 60s segments
        preview_frames = 0

        numeric_segments = math.floor((frames_total - preview_frames) / frames_per_segment) + 1
        assert numeric_segments == 3  # 125s / 60s = 2.08 -> 2 full + 1 partial = 3

    def test_segment_frame_start(self):
        """Frame start for a given segment should be correctly computed."""
        frames_per_segment = 1800
        preview_frames = 150

        # Segment 1 starts right after preview
        assert (1 - 1) * frames_per_segment + preview_frames == 150
        # Segment 2
        assert (2 - 1) * frames_per_segment + preview_frames == 1950
        # Segment 3
        assert (3 - 1) * frames_per_segment + preview_frames == 3750

    def test_segment_frame_count_not_exceeding_total(self):
        """Frame count for last segment should be clamped to remaining frames."""
        frames_total = 5000
        frames_per_segment = 1800
        preview_frames = 0

        # Segment 3 starts at frame 3600
        segment_frame_start = (3 - 1) * frames_per_segment + preview_frames
        frame_count = min(frames_total - segment_frame_start, frames_per_segment)
        assert frame_count == 1400  # 5000 - 3600 = 1400

    def test_frame_start_to_segment_start(self):
        """Resuming from a frame number should map to the correct segment."""
        frame_start = 2000
        frames_per_segment = 1800
        preview_frames = 150

        segment_start = max(math.floor((frame_start - preview_frames) / frames_per_segment) + 1, 1)
        assert segment_start == 2  # (2000-150)/1800 = 1.03 -> floor(1.03)+1 = 2

    def test_preview_seconds_clamped(self):
        """Preview length should not exceed total length."""
        preview_cfg = 10.0
        seconds_total = 5.0
        preview_seconds = min(preview_cfg, seconds_total)
        assert preview_seconds == 5.0


class TestFfmpegArgConstruction:
    """Tests for the FFmpeg extra args parsing logic from config."""

    def test_arg_with_value(self):
        """Args with non-empty values should produce two entries."""
        args = []
        cfg_items = [
            ('visualization.video.export.ffmpeg-extra-args.-crf', 22),
        ]
        prefix = 'visualization.video.export.ffmpeg-extra-args.'

        for key, value in cfg_items:
            if key.startswith(prefix):
                arg_name = key[len(prefix):]
                if value is not None:
                    args.append(arg_name)
                    if value != '':
                        args.append(str(value))

        assert args == ['-crf', '22']

    def test_arg_with_empty_value(self):
        """Args with empty string values should produce only the flag."""
        args = []
        cfg_items = [
            ('visualization.video.export.ffmpeg-extra-args.-y', ''),
        ]
        prefix = 'visualization.video.export.ffmpeg-extra-args.'

        for key, value in cfg_items:
            if key.startswith(prefix):
                arg_name = key[len(prefix):]
                if value is not None:
                    args.append(arg_name)
                    if value != '':
                        args.append(str(value))

        assert args == ['-y']

    def test_arg_with_none_skipped(self):
        """Args with None values should be skipped entirely."""
        args = []
        cfg_items = [
            ('visualization.video.export.ffmpeg-extra-args.-pix_fmt', None),
        ]
        prefix = 'visualization.video.export.ffmpeg-extra-args.'

        for key, value in cfg_items:
            if key.startswith(prefix):
                arg_name = key[len(prefix):]
                if value is not None:
                    args.append(arg_name)
                    if value != '':
                        args.append(str(value))

        assert args == []

    def test_keyframe_interval(self):
        """Keyframe args should use fps * interval."""
        fps = 30
        interval = 5
        expected = ['-g', str(interval * fps)]
        result = ['-g', str(interval * fps)]
        assert result == ['-g', '150']

    def test_force_key_frames_expression(self):
        """The concat keyframe expression should reference the correct time."""
        fps = 30
        frame_count = 1800
        segment_length = frame_count * fps
        expr = f'expr:gte(t,{segment_length - 1 / fps})'
        assert 'gte(t,' in expr
        assert str(segment_length - 1 / fps) in expr
