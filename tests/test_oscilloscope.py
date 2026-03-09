import numpy as np
import pytest

from estimpy.visualization.base import AxisTypes, Visualization
from estimpy.visualization.oscilloscope import OscilloscopeMixin


def _make_mixin_with_handle_id():
    """Create an OscilloscopeMixin with the _get_axis_handle_id method attached."""
    mixin = OscilloscopeMixin()
    mixin._get_axis_handle_id = Visualization._get_axis_handle_id
    return mixin


class TestFindTriggerZeroCrossing:
    """Tests for the zero-crossing trigger detection algorithm."""

    @pytest.fixture
    def mixin(self):
        """Create a bare OscilloscopeMixin with required config values injected."""
        import estimpy as es
        es.cfg['analysis.oscilloscope.silence-threshold'] = 0.01
        es.cfg['analysis.oscilloscope.trigger-hysteresis'] = 0.3
        return OscilloscopeMixin()

    def test_sine_wave_finds_crossing(self, mixin):
        """Should find a rising zero-crossing in a clean sine wave."""
        t = np.linspace(0, 2 * np.pi * 3, 1000, dtype=np.float32)
        waveform = np.sin(t)
        idx = mixin._dr_osc_find_trigger_zero_crossing(waveform)
        # Should find a crossing somewhere after the first negative dip
        assert idx > 0
        # At the crossing: waveform[idx] <= 0 and waveform[idx+1] > 0
        assert waveform[idx] <= 0
        assert waveform[idx + 1] > 0

    def test_silence_returns_zero(self, mixin):
        """Silent signal should return index 0."""
        waveform = np.zeros(100, dtype=np.float32)
        idx = mixin._dr_osc_find_trigger_zero_crossing(waveform)
        assert idx == 0

    def test_all_positive_returns_zero(self, mixin):
        """Signal that never goes negative can't arm the trigger."""
        waveform = np.ones(100, dtype=np.float32) * 0.5
        idx = mixin._dr_osc_find_trigger_zero_crossing(waveform)
        assert idx == 0

    def test_single_crossing(self, mixin):
        """Waveform with exactly one rising crossing."""
        waveform = np.array([-0.5, -0.3, -0.1, 0.1, 0.3, 0.5], dtype=np.float32)
        idx = mixin._dr_osc_find_trigger_zero_crossing(waveform)
        assert idx == 2  # waveform[2] <= 0, waveform[3] > 0


class TestFindTriggerCorrelation:
    @pytest.fixture
    def mixin(self):
        return OscilloscopeMixin()

    def test_identical_signals(self, mixin):
        """Template matching itself should give high quality and offset 0."""
        template = np.sin(np.linspace(0, 2 * np.pi, 100, dtype=np.float32))
        search = np.concatenate([template, np.zeros(50, dtype=np.float32)])
        offset, quality = mixin._dr_osc_find_trigger_correlation(search, template)
        assert offset == 0
        assert quality > 0.95

    def test_shifted_signal(self, mixin):
        """Template shifted by known offset should be found at that offset."""
        template = np.sin(np.linspace(0, 2 * np.pi * 3, 100, dtype=np.float32))
        shift = 20
        search = np.concatenate([np.zeros(shift, dtype=np.float32), template,
                                 np.zeros(50, dtype=np.float32)])
        offset, quality = mixin._dr_osc_find_trigger_correlation(search, template)
        assert offset == shift
        assert quality > 0.9

    def test_zero_template_returns_zero(self, mixin):
        """Zero-energy template should return offset 0, quality 0."""
        template = np.zeros(50, dtype=np.float32)
        search = np.sin(np.linspace(0, 2 * np.pi, 100, dtype=np.float32))
        offset, quality = mixin._dr_osc_find_trigger_correlation(search, template)
        assert offset == 0
        assert quality == 0.0

    def test_short_search_buffer(self, mixin):
        """Search buffer shorter than template should return 0, 0."""
        template = np.ones(100, dtype=np.float32)
        search = np.ones(50, dtype=np.float32)
        offset, quality = mixin._dr_osc_find_trigger_correlation(search, template)
        assert offset == 0
        assert quality == 0.0


class TestOscComputeBox:
    """Tests for oscilloscope box geometry calculation."""

    @pytest.fixture
    def mixin_with_regions(self):
        """Create a mixin with mock data regions for box computation."""
        import estimpy as es
        mixin = _make_mixin_with_handle_id()
        mixin._data_regions = {
            'amplitude_0': (0, 0, 1920, 200),
            'spectrogram_0': (0, 200, 1920, 600),
        }
        mixin._channel_layout = [(0, False)]
        es.cfg['visualization.style.oscilloscope.width-ratio'] = 0.3
        es.cfg['visualization.style.oscilloscope.height-ratio'] = 0.5
        return mixin

    def test_returns_tuple(self, mixin_with_regions):
        box = mixin_with_regions._dr_osc_compute_box(0)
        assert box is not None
        assert len(box) == 4

    def test_box_within_panel(self, mixin_with_regions):
        box = mixin_with_regions._dr_osc_compute_box(0)
        bx0, by0, bx1, by1 = box
        # Box should be within the combined panel area
        assert bx0 >= 0
        assert by0 >= 0
        assert bx1 <= 1920
        assert by1 <= 600

    def test_box_dimensions_positive(self, mixin_with_regions):
        box = mixin_with_regions._dr_osc_compute_box(0)
        bx0, by0, bx1, by1 = box
        assert bx1 > bx0
        assert by1 > by0

    def test_tiny_panel_returns_none(self):
        """Very small panels should return None (box too small to be useful)."""
        import estimpy as es
        mixin = _make_mixin_with_handle_id()
        mixin._data_regions = {
            'amplitude_0': (0, 0, 30, 5),
            'spectrogram_0': (0, 5, 30, 10),
        }
        mixin._channel_layout = [(0, False)]
        es.cfg['visualization.style.oscilloscope.width-ratio'] = 0.3
        es.cfg['visualization.style.oscilloscope.height-ratio'] = 0.5
        box = mixin._dr_osc_compute_box(0)
        assert box is None
