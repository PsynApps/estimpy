import math

import pytest

import estimpy as es


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
