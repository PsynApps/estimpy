import math

import matplotlib.colors
import numpy as np
import pytest

import estimpy as es
from estimpy.visualization import (
    _alpha_color,
    _calculate_spectrogram_panel_height,
    _derive_channel_colormap,
    _parse_resolution,
)
from estimpy.visualization.base import (
    AxisTypes,
    VisualizationMode,
    Visualization,
)


class TestParseResolution:
    def test_standard_resolution(self):
        assert _parse_resolution('1920x1080') == (1920, 1080)

    def test_4k_resolution(self):
        assert _parse_resolution('3840x2160') == (3840, 2160)

    def test_with_spaces(self):
        assert _parse_resolution(' 1920 x 1080 ') == (1920, 1080)

    def test_invalid_format_no_separator(self):
        with pytest.raises(ValueError, match='Invalid resolution format'):
            _parse_resolution('1920-1080')

    def test_invalid_format_non_numeric(self):
        with pytest.raises(ValueError):
            _parse_resolution('widexhigh')

    def test_square(self):
        assert _parse_resolution('1080x1080') == (1080, 1080)


class TestAlphaColor:
    def test_full_opacity(self):
        result = _alpha_color('white', 'black', 1.0)
        assert result == '#FFFFFF'

    def test_zero_opacity(self):
        result = _alpha_color('white', 'black', 0.0)
        assert result == '#000000'

    def test_half_opacity_white_on_black(self):
        result = _alpha_color('white', 'black', 0.5)
        # 0.5 * 255 + 0.5 * 0 = 127.5 -> 128
        assert result == '#808080'

    def test_color_on_white(self):
        result = _alpha_color('red', 'white', 0.5)
        # R: 0.5*1 + 0.5*1 = 1.0 -> FF, G: 0.5*0 + 0.5*1 = 0.5 -> 80, B: same as G
        assert result == '#FF8080'

    def test_returns_hex_string(self):
        result = _alpha_color('blue', 'black', 0.3)
        assert result.startswith('#')
        assert len(result) == 7


class TestDeriveChannelColormap:
    def test_returns_listed_colormap(self):
        cmap = _derive_channel_colormap('jet', '#FF0000')
        assert isinstance(cmap, matplotlib.colors.ListedColormap)

    def test_colormap_has_correct_length(self):
        n = 128
        cmap = _derive_channel_colormap('jet', '#00FF00', n_samples=n)
        assert len(cmap.colors) == n

    def test_default_sample_count(self):
        cmap = _derive_channel_colormap('jet', '#0000FF')
        assert len(cmap.colors) == 256

    def test_values_in_valid_range(self):
        cmap = _derive_channel_colormap('jet', '#FF0000', background_color='#1A1A1A')
        colors = np.array(cmap.colors)
        assert np.all(colors >= 0.0)
        assert np.all(colors <= 1.0)

    def test_unsaturated_colormap_returns_original(self):
        """A grayscale colormap has no saturated samples and should be returned unchanged."""
        cmap = _derive_channel_colormap('gray', '#FF0000')
        original = matplotlib.colormaps['gray']
        positions = np.linspace(0, 1, 256)
        np.testing.assert_array_almost_equal(
            cmap(positions), original(positions), decimal=5)

    def test_with_background_color(self):
        """Background color should darken the base region at position 0."""
        cmap_no_bg = _derive_channel_colormap('jet', '#FF0000', n_samples=64)
        cmap_with_bg = _derive_channel_colormap('jet', '#FF0000',
                                                 background_color='#000000', n_samples=64)
        # First few colors should be darker with black background
        no_bg_lum = np.array(cmap_no_bg.colors[0][:3]) @ [0.2126, 0.7152, 0.0722]
        with_bg_lum = np.array(cmap_with_bg.colors[0][:3]) @ [0.2126, 0.7152, 0.0722]
        assert with_bg_lum <= no_bg_lum + 1e-6


class TestCalculateSpectrogramPanelHeight:
    def test_mono_basic(self):
        height = _calculate_spectrogram_panel_height(1080, n_channels=1)
        assert 0 < height < 1080

    def test_stereo_smaller_than_mono(self):
        mono = _calculate_spectrogram_panel_height(1080, n_channels=1)
        stereo = _calculate_spectrogram_panel_height(1080, n_channels=2)
        assert stereo < mono

    def test_triphase_smaller_than_stereo(self):
        stereo = _calculate_spectrogram_panel_height(1080, n_channels=2)
        triphase = _calculate_spectrogram_panel_height(1080, n_channels=3, triphase=True)
        assert triphase < stereo

    def test_title_reduces_height(self):
        without_title = _calculate_spectrogram_panel_height(1080, n_channels=2)
        with_title = _calculate_spectrogram_panel_height(1080, n_channels=2, title_enabled=True)
        assert with_title < without_title

    def test_scrub_reduces_height(self):
        without_scrub = _calculate_spectrogram_panel_height(1080, n_channels=2)
        with_scrub = _calculate_spectrogram_panel_height(1080, n_channels=2, include_scrub=True)
        assert with_scrub < without_scrub

    def test_proportional_to_figure_height(self):
        h1 = _calculate_spectrogram_panel_height(1080, n_channels=2)
        h2 = _calculate_spectrogram_panel_height(2160, n_channels=2)
        assert abs(h2 / h1 - 2.0) < 0.01

    def test_triphase_with_two_channels_uses_stereo(self):
        """Triphase flag with only 2 channels should use stereo layout."""
        triphase_2ch = _calculate_spectrogram_panel_height(1080, n_channels=2, triphase=True)
        stereo = _calculate_spectrogram_panel_height(1080, n_channels=2)
        assert triphase_2ch == stereo


class TestSpectrogramScaleText:
    def test_hz_below_1000(self):
        assert Visualization._get_spectrogram_scale_text(500) == '500 Hz'

    def test_khz_exact(self):
        assert Visualization._get_spectrogram_scale_text(2000) == '2 kHz'

    def test_khz_fractional(self):
        assert Visualization._get_spectrogram_scale_text(2500) == '2.5 kHz'

    def test_hz_boundary(self):
        assert Visualization._get_spectrogram_scale_text(999) == '999 Hz'

    def test_khz_boundary(self):
        assert Visualization._get_spectrogram_scale_text(1000) == '1 kHz'

    def test_large_frequency(self):
        assert Visualization._get_spectrogram_scale_text(20000) == '20 kHz'


class TestSpectrogramYticks:
    def test_below_1000(self):
        ticks = Visualization._get_spectrogram_yticks(800)
        assert list(ticks) == [0, 250, 500, 750]

    def test_below_2000(self):
        ticks = Visualization._get_spectrogram_yticks(1500)
        assert list(ticks) == [0, 500, 1000]

    def test_below_10000(self):
        ticks = Visualization._get_spectrogram_yticks(5000)
        assert list(ticks) == [0, 1000, 2000, 3000, 4000]

    def test_below_20000(self):
        ticks = Visualization._get_spectrogram_yticks(15000)
        assert list(ticks) == [0, 2500, 5000, 7500, 10000, 12500]

    def test_above_20000(self):
        ticks = Visualization._get_spectrogram_yticks(25000)
        assert list(ticks) == [0, 5000, 10000, 15000, 20000]


class TestAxisHandleId:
    def test_with_channel(self):
        assert Visualization._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=0) == 'amplitude_0'

    def test_without_channel(self):
        assert Visualization._get_axis_handle_id(type=AxisTypes.TITLE) == 'title'

    def test_spectrogram_channel(self):
        assert Visualization._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=2) == 'spectrogram_2'


class TestGetChannelStyleCfg:
    def test_returns_channel_config(self):
        assert Visualization._get_channel_style_cfg(0)['color'] == '#4799e8'
        assert Visualization._get_channel_style_cfg(1)['color'] == '#b775ff'
        assert Visualization._get_channel_style_cfg(2)['color'] == '#e06cb7'

    def test_labels(self):
        assert Visualization._get_channel_style_cfg(0)['label'] == 'A'
        assert Visualization._get_channel_style_cfg(1)['label'] == 'B'
        assert Visualization._get_channel_style_cfg(2)['label'] == 'T'

    def test_out_of_range_falls_back_to_ch0(self):
        cfg = Visualization._get_channel_style_cfg(99)
        assert cfg['color'] == '#4799e8'


class TestGetAmplitudeStyleCfg:
    def test_peak_color_inherits_channel_color(self):
        """When peak-color is ~, it should inherit the channel identity color."""
        cfg = Visualization._get_amplitude_style_cfg(0)
        assert cfg['peak-color'] == '#4799e8'
        assert cfg['color'] == '#4799e8'

    def test_rms_color_derived(self):
        """rms-color should be derived (not None) even when config is ~."""
        cfg = Visualization._get_amplitude_style_cfg(0)
        assert cfg['rms-color'] is not None
        assert cfg['rms-color'].startswith('#')

    def test_background_color_derived(self):
        """background-color should be derived (not None) even when config is ~."""
        cfg = Visualization._get_amplitude_style_cfg(0)
        assert cfg['background-color'] is not None
        assert cfg['background-color'].startswith('#')


class TestEnums:
    def test_axis_types_values(self):
        assert AxisTypes.AMPLITUDE == 'amplitude'
        assert AxisTypes.SPECTROGRAM == 'spectrogram'
        assert AxisTypes.TITLE == 'title'
        assert AxisTypes.CONTROLS == 'controls'
        assert AxisTypes.AMPLITUDE_SCRUB == 'amplitude_scrub'

    def test_visualization_mode_values(self):
        assert VisualizationMode.DISPLAY == 0
        assert VisualizationMode.EXPORT == 1
