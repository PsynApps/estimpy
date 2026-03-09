import math

import numpy as np
import pytest

import estimpy as es
from estimpy.visualization.video import VideoVisualization


class TestFrameToTime:
    """Tests for VideoVisualization._frame_to_time (via a minimal instance)."""

    def test_frame_zero(self, video_viz):
        assert video_viz._frame_to_time(0) == 0.0

    def test_frame_at_fps(self, video_viz):
        """Frame number equal to fps should be 1 second."""
        assert video_viz._frame_to_time(30) == pytest.approx(1.0)

    def test_fractional_frame(self, video_viz):
        assert video_viz._frame_to_time(15) == pytest.approx(0.5)


class TestTimeToFrame:
    def test_zero(self, video_viz):
        assert video_viz._time_to_frame(0) == 0

    def test_one_second(self, video_viz):
        assert video_viz._time_to_frame(1.0) == 30

    def test_fractional_floors(self, video_viz):
        """Should floor partial frames."""
        assert video_viz._time_to_frame(0.51) == math.floor(0.51 * 30)


class TestGetWindowRange:
    def test_centered_window(self, video_viz):
        """Window should center on t when not near edges."""
        wmin, wmax = video_viz._get_window_range(t=0.5, total_length=1.0, window_length=0.2)
        assert wmin == pytest.approx(0.4)
        assert wmax == pytest.approx(0.6)

    def test_clamped_at_start(self, video_viz):
        """Window should clamp to 0 at the start."""
        wmin, wmax = video_viz._get_window_range(t=0.05, total_length=1.0, window_length=0.2)
        assert wmin == pytest.approx(0.0)
        assert wmax == pytest.approx(0.2)

    def test_clamped_at_end(self, video_viz):
        """Window should clamp at the end."""
        wmin, wmax = video_viz._get_window_range(t=0.95, total_length=1.0, window_length=0.2)
        assert wmin == pytest.approx(0.8)
        assert wmax == pytest.approx(1.0)

    def test_window_larger_than_total(self, video_viz):
        """When window is larger than total length, min=0 and max=total."""
        wmin, wmax = video_viz._get_window_range(t=0.5, total_length=1.0, window_length=2.0)
        assert wmin == pytest.approx(0.0)
        assert wmax == pytest.approx(1.0)

    def test_round_bounds(self, video_viz):
        """round_bounds should floor the half-window length."""
        wmin, wmax = video_viz._get_window_range(t=50, total_length=100, window_length=21,
                                                   round_bounds=True)
        # half = floor(10.5) = 10
        assert wmin == pytest.approx(40)
        assert wmax == pytest.approx(60)


class TestDrComputeScroll:
    def test_normal_scroll(self, video_viz):
        """Small forward scroll should return non-negative integer."""
        video_viz._dr_prev_window_min = 0.0
        video_viz._dr_pixels_per_second = 100.0
        video_viz._dr_panel_width = 1920
        video_viz._dr_scroll_accumulator = 0.0

        shift = video_viz._dr_compute_scroll(0.05)
        assert shift == 5  # 0.05 * 100 = 5.0

    def test_subpixel_accumulation(self, video_viz):
        """Sub-pixel deltas should accumulate across calls."""
        video_viz._dr_prev_window_min = 0.0
        video_viz._dr_pixels_per_second = 100.0
        video_viz._dr_panel_width = 1920
        video_viz._dr_scroll_accumulator = 0.0

        # 0.003 * 100 = 0.3 pixels -> rounds to 0
        shift1 = video_viz._dr_compute_scroll(0.003)
        assert shift1 == 0
        # Accumulator now has 0.3

        video_viz._dr_prev_window_min = 0.003
        # Another 0.3 -> total 0.6 -> rounds to 1
        shift2 = video_viz._dr_compute_scroll(0.006)
        assert shift2 == 1

    def test_large_jump_forces_rerender(self, video_viz):
        """Jump larger than panel width should return -1."""
        video_viz._dr_prev_window_min = 0.0
        video_viz._dr_pixels_per_second = 100.0
        video_viz._dr_panel_width = 100
        video_viz._dr_scroll_accumulator = 0.0

        shift = video_viz._dr_compute_scroll(2.0)  # 200 pixels > 100 panel width
        assert shift == -1

    def test_backward_jump_forces_rerender(self, video_viz):
        """Backward scroll should return -1."""
        video_viz._dr_prev_window_min = 1.0
        video_viz._dr_pixels_per_second = 100.0
        video_viz._dr_panel_width = 1920
        video_viz._dr_scroll_accumulator = 0.0

        shift = video_viz._dr_compute_scroll(0.5)
        assert shift == -1


@pytest.fixture
def video_viz(synthetic_stereo_audio):
    """Create a minimal VideoVisualization for testing pure-logic methods.
    Does not create matplotlib figures or render frames."""
    es.cfg['visualization.video.export.fps'] = 30
    es.cfg['visualization.video.export.window-length'] = 5.0
    return VideoVisualization(es_audio=synthetic_stereo_audio, fps=30)
