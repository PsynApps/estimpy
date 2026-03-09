"""Visualization subpackage for EstimPy.

Re-exports the public API and handles configuration event processing.
Internal helpers (_parse_resolution, _alpha_color, _derive_channel_colormap)
and the config.updated listener live here since they serve the subpackage
as a whole rather than belonging to any single class.
"""

import colorsys
import math
import typing

import estimpy as es
import matplotlib
import matplotlib.colors
import matplotlib.font_manager
import matplotlib.pyplot
import numpy as np
from PIL import ImageFont

# Re-export public API
from estimpy.visualization.base import (
    AxisScaleText,
    AxisTypes,
    Visualization,
    VisualizationMode,
    set_optimal_nfft,
    show_image,
)
from estimpy.visualization.video import VideoVisualization


def _alpha_color(color, bg_color, alpha) -> str:
    """Apply alpha blending with RGB colors (not RGBA)."""
    rgb = matplotlib.colors.to_rgb(color)
    bg_rgb = matplotlib.colors.to_rgb(bg_color)
    alpha_rgb = [alpha * c1 + (1 - alpha) * c2 for (c1, c2) in zip(rgb, bg_rgb)]
    return '#' + ''.join(f'{i:02X}' for i in [round(255 * x) for x in alpha_rgb])


def _derive_channel_colormap(base_cmap_name: str, peak_color: str, background_color: str = None,
                              radius_degrees: float = 30.0,
                              n_samples: int = 256) -> matplotlib.colors.ListedColormap:
    """Derive a channel-specific colormap by recoloring the base region to match a peak color.

    The "base region" is where the colormap's hue stays near its starting hue (e.g., the blue
    region of jet). This region is recolored to match the channel's color hue and saturation,
    preserving the original luminance profile. The "signal region" (rapidly changing hues) is
    left untouched, so spectral features look identical across all channels.

    :param radius_degrees: Hue distance in degrees (0-180) from the base hue within which
        colormap samples are recolored. The outer 25% of the radius is a cosine transition zone.

    If background_color is provided, the luminance at the bottom of the base region is pushed
    down to match the amplitude panel's background color, creating a smooth visual transition
    between the two panels at silence.
    """
    base_cmap = matplotlib.colormaps[base_cmap_name]

    # Sample the base colormap
    positions = np.linspace(0.0, 1.0, n_samples)
    base_rgba = base_cmap(positions)
    base_rgb = base_rgba[:, :3]

    # Convert all samples to HLS
    base_hls = np.array([colorsys.rgb_to_hls(r, g, b) for r, g, b in base_rgb])
    # Columns: [0]=hue (0-1), [1]=lightness (0-1), [2]=saturation (0-1)

    # Identify the base hue from the first sample with sufficient saturation
    saturation_threshold = 0.2
    saturated_mask = base_hls[:, 2] > saturation_threshold
    if not np.any(saturated_mask):
        return base_cmap

    base_hue = base_hls[np.argmax(saturated_mask), 0]

    # Parse the channel color into HLS (only the hue is used for recoloring)
    peak_rgb = matplotlib.colors.to_rgb(peak_color)
    peak_h, _, _ = colorsys.rgb_to_hls(*peak_rgb)

    # Compute angular hue distance from base hue (circular, in [0, 0.5] range)
    hue_dist = np.abs(base_hls[:, 0] - base_hue)
    hue_dist = np.minimum(hue_dist, 1.0 - hue_dist)

    # Unsaturated samples are treated as base region (dark/black start should be recolored)
    hue_dist[~saturated_mask] = 0.0

    # Blend weights: 1.0 in base region, 0.0 in signal region, smooth cosine transition
    # The outer 25% of the radius is a transition zone
    outer_threshold = radius_degrees / 360.0
    inner_threshold = 0.75 * outer_threshold

    blend = np.ones(n_samples)
    transition_mask = (hue_dist > inner_threshold) & (hue_dist < outer_threshold)
    t = (hue_dist[transition_mask] - inner_threshold) / (outer_threshold - inner_threshold)
    blend[transition_mask] = 0.5 * (1.0 + np.cos(np.pi * t))
    blend[hue_dist >= outer_threshold] = 0.0

    # Compute background relative luminance for darkening
    lum_weights = np.array([0.2126, 0.7152, 0.0722])
    if background_color is not None:
        bg_Y = np.array(matplotlib.colors.to_rgb(background_color)) @ lum_weights
    else:
        bg_Y = None

    # Recolor blended positions
    result_rgb = base_rgb.copy()
    recolor_mask = blend > 0.0
    recolor_indices = np.where(recolor_mask)[0]
    max_recolor_idx = recolor_indices[-1] if len(recolor_indices) > 0 else 0

    for i in recolor_indices:
        # Replace hue, keep original luminance and saturation
        recolored = np.array(colorsys.hls_to_rgb(peak_h, base_hls[i, 1], base_hls[i, 2]))

        # Scale to match the original's perceptual brightness,
        # compensating for HLS lightness non-uniformity across hues
        original_Y = base_rgb[i] @ lum_weights
        recolored_Y = recolored @ lum_weights
        if recolored_Y > 0:
            recolored = np.clip(recolored * (original_Y / recolored_Y), 0, 1)

        # Darken toward background brightness at position 0, reaching original brightness
        # at the edge of the recolored region
        if bg_Y is not None and max_recolor_idx > 0:
            position_factor = i / max_recolor_idx
            matched_Y = recolored @ lum_weights
            target_Y = bg_Y + (matched_Y - bg_Y) * position_factor
            if matched_Y > 0:
                recolored = np.clip(recolored * (target_Y / matched_Y), 0, 1)

        result_rgb[i] = blend[i] * recolored + (1.0 - blend[i]) * base_rgb[i]

    result_rgba = np.column_stack([result_rgb, base_rgba[:, 3]])
    return matplotlib.colors.ListedColormap(result_rgba)


def _calculate_spectrogram_panel_height(figure_height: float, n_channels: int,
                                        triphase: bool = False,
                                        title_enabled: bool = False,
                                        include_scrub: bool = False) -> float:
    """Calculate the pixel height of one spectrogram panel from layout configuration.

    Uses the configured subplot height ratios to determine what fraction of the
    total figure height is allocated to each spectrogram panel. Accounts for
    title, amplitude, and optional scrub panels.

    :param figure_height: Total figure height in pixels.
    :param n_channels: Number of audio channels (1=mono, 2=stereo, 3=triphase).
    :param triphase: Whether triphase display mode is active.
    :param title_enabled: Whether the title panel is shown.
    :param include_scrub: Whether scrub panels are included (video mode).
    :return: Height of one spectrogram panel in pixels.
    """
    if triphase and n_channels >= 3:
        ratio_key = 'triphase'
        n_display = 3
    elif n_channels >= 2:
        ratio_key = 'stereo'
        n_display = 2
    else:
        ratio_key = 'mono'
        n_display = 1

    spec_ratio = es.cfg[f'visualization.style.subplot-height-ratios.spectrogram.{ratio_key}']
    amp_ratio = es.cfg[f'visualization.style.subplot-height-ratios.amplitude.{ratio_key}']

    total_ratio = n_display * (spec_ratio + amp_ratio)

    if title_enabled:
        total_ratio += es.cfg['visualization.style.subplot-height-ratios.title']

    if include_scrub:
        n_scrub = min(n_channels, 2)
        total_ratio += n_scrub * (amp_ratio / 2)

    if total_ratio <= 0:
        return figure_height

    return figure_height * spec_ratio / total_ratio


def _parse_resolution(resolution) -> typing.Tuple[int, int]:
    try:
        width, height = resolution.split('x')
        width = int(width.strip())
        height = int(height.strip())
        return width, height
    except ValueError:
        raise ValueError(
            'Invalid resolution format. Provide the resolution as a string in the format "widthxheight", e.g. "1920x1080".')


def _on_config_updated():
    """Recompute derived config values from primary config keys.

    Derived keys injected into es.cfg (not present in default.yaml):
        Resolution parsing (from *.size strings):
            visualization.image.display.width / .height
            visualization.image.export.width / .height
            visualization.video.display.width / .height
            visualization.video.export.width / .height
        Font resolution:
            visualization.style.font.text.properties      (FontProperties)
            visualization.style.font.text.mpl-fontproperties (FontProperties, TTC-safe)
            visualization.style.font.text.file             (resolved font file path)
            visualization.style.font.text.face-index       (TTC face index)
            visualization.style.font.symbols.properties    (FontProperties)
            visualization.style.font.symbols.file          (resolved font file path)
        Layout:
            visualization.style.title.max-width            (pixels, from width-factor-max)
        Channel styling (list of dicts, resolved from per-channel keys):
            visualization.style.channels                   (color, label)
            visualization.style.amplitude.channels         (color, peak-color, rms-color, background-color)
            visualization.style.spectrogram.channels       (color-map, possibly derived)
    """
    # Display sizes
    es.cfg['visualization.image.display.width'], es.cfg['visualization.image.display.height'] = _parse_resolution(
        es.cfg['visualization.image.display.size'])
    es.cfg['visualization.video.display.width'], es.cfg['visualization.video.display.height'] = _parse_resolution(
        es.cfg['visualization.video.display.size'])

    # Image size
    es.cfg['visualization.image.export.width'], es.cfg['visualization.image.export.height'] = _parse_resolution(
        es.cfg['visualization.image.export.size'])

    # Video size
    es.cfg['visualization.video.export.width'], es.cfg['visualization.video.export.height'] = _parse_resolution(
        es.cfg['visualization.video.export.size'])

    # Font — Text
    _families = [item.strip() for item in es.cfg['visualization.style.font.text.family'].split(',')]
    _weight = es.cfg['visualization.style.font.text.weight']
    es.cfg['visualization.style.font.text.properties'] = matplotlib.font_manager.FontProperties(
        family=_families, weight=_weight)
    es.cfg['visualization.style.font.text.file'] = matplotlib.font_manager.findfont(
        es.cfg['visualization.style.font.text.properties'])

    # Determine the correct face index for TTC (TrueType Collection) files.
    # Pillow defaults to index 0 (usually Regular); we need to find the matching face.
    # Stored as a derived config key so all modules can access it without cross-module state.
    es.cfg['visualization.style.font.text.face-index'] = 0
    _font_file = es.cfg['visualization.style.font.text.file']
    if _font_file.lower().endswith('.ttc'):
        _target_weight = _weight.lower()
        for _i in range(64):
            try:
                _face = ImageFont.truetype(_font_file, 12, index=_i)
                _style = _face.getname()[1].lower()
                if _target_weight in _style:
                    es.cfg['visualization.style.font.text.face-index'] = _i
                    break
            except OSError:
                break

    # Matplotlib's FT2Font cannot select face indices from TTC files, so bold/italic
    # variants in TTC files won't render correctly. Find a non-TTC font file that
    # matches the requested weight for matplotlib text rendering.
    _mpl_font_file = None
    _weight_num = es.cfg['visualization.style.font.text.properties'].get_weight()
    if isinstance(_weight_num, str):
        _weight_num = {'ultralight': 100, 'light': 200, 'normal': 400, 'regular': 400,
                       'book': 400, 'medium': 500, 'roman': 500, 'semibold': 600,
                       'demibold': 600, 'demi': 600, 'bold': 700, 'heavy': 800,
                       'extra bold': 800, 'black': 900}.get(_weight_num, 400)
    if _font_file.lower().endswith('.ttc') and _weight_num >= 700:
        # Search configured font families for a non-TTC bold font
        for _family in _families:
            for _entry in matplotlib.font_manager.fontManager.ttflist:
                if (_entry.name.lower() == _family.lower()
                        and _entry.weight >= 700
                        and _entry.style == 'normal'
                        and not _entry.fname.lower().endswith('.ttc')):
                    _mpl_font_file = _entry.fname
                    break
            if _mpl_font_file:
                break
    if _mpl_font_file:
        es.cfg['visualization.style.font.text.mpl-fontproperties'] = \
            matplotlib.font_manager.FontProperties(fname=_mpl_font_file)
    else:
        es.cfg['visualization.style.font.text.mpl-fontproperties'] = \
            matplotlib.font_manager.FontProperties(family=_families, weight=_weight)

    # Set matplotlib font configuration
    matplotlib.pyplot.rcParams['font.family'] = es.cfg['visualization.style.font.text.properties'].get_family()
    matplotlib.pyplot.rcParams['font.weight'] = es.cfg['visualization.style.font.text.properties'].get_weight()

    # Symbols
    es.cfg['visualization.style.font.symbols.properties'] = matplotlib.font_manager.FontProperties(
        family=[item.strip() for item in es.cfg['visualization.style.font.symbols.family'].split(',')])
    es.cfg['visualization.style.font.symbols.file'] = matplotlib.font_manager.findfont(
        es.cfg['visualization.style.font.symbols.properties'])

    # Title
    es.cfg['visualization.style.title.max-width'] = math.floor(
        es.cfg['visualization.style.title.width-factor-max'] * es.cfg['visualization.image.display.width'])

    # --- Resolve channel identity (color + label) ---
    # Enumerate channels from visualization.style.channels.chN.color keys
    channel_prefix = 'visualization.style.channels.'
    max_channel = 0
    for key in es.cfg.keys():
        if key.startswith(channel_prefix):
            parts = key[len(channel_prefix):].split('.')
            if parts[0].startswith('ch'):
                channel_number = int(parts[0][2:])
                max_channel = max(max_channel, channel_number)

    n_channels = max_channel + 1
    es.cfg['visualization.style.channels'] = [None] * n_channels
    for i_channel in range(n_channels):
        es.cfg['visualization.style.channels'][i_channel] = {
            'color': es.cfg[f'visualization.style.channels.ch{i_channel}.color'],
            'label': es.cfg.get(f'visualization.style.channels.ch{i_channel}.label', ''),
        }

    # --- Resolve amplitude channel styling ---
    # Each amplitude property falls back to the channel identity color
    es.cfg['visualization.style.amplitude.channels'] = [None] * n_channels
    for i_channel in range(n_channels):
        channel_color = es.cfg['visualization.style.channels'][i_channel]['color']

        peak_color = es.cfg.get(f'visualization.style.amplitude.channels.ch{i_channel}.peak-color')
        if peak_color is None:
            peak_color = channel_color

        rms_color = es.cfg.get(f'visualization.style.amplitude.channels.ch{i_channel}.rms-color')
        if rms_color is None:
            rms_color = _alpha_color(channel_color, (1, 1, 1),
                                     es.cfg['visualization.style.amplitude.rms-alpha'])

        background_color = es.cfg.get(f'visualization.style.amplitude.channels.ch{i_channel}.background-color')
        if background_color is None:
            background_color = _alpha_color(channel_color, (0, 0, 0),
                                            es.cfg['visualization.style.amplitude.background-alpha'])

        es.cfg['visualization.style.amplitude.channels'][i_channel] = {
            'color': channel_color,
            'peak-color': peak_color,
            'rms-color': rms_color,
            'background-color': background_color,
        }

    # --- Resolve per-channel spectrogram colormaps ---
    # 1. If an explicit per-channel override is set, use it directly
    # 2. Otherwise, derive from the base colormap (with color matching if enabled)
    base_cmap_name = es.cfg['visualization.style.spectrogram.color-map']
    match_channel_color = es.cfg['visualization.style.spectrogram.match-channel-color']

    resolved_spec_channels = [None] * n_channels
    for i_channel in range(n_channels):
        channel_override = es.cfg.get(f'visualization.style.spectrogram.channels.ch{i_channel}.color-map')

        if channel_override is not None:
            resolved_spec_channels[i_channel] = {'color-map': channel_override}
        else:
            cmap_registry_name = f'_estimpy_ch{i_channel}'

            if cmap_registry_name in matplotlib.colormaps:
                matplotlib.colormaps.unregister(name=cmap_registry_name)

            if match_channel_color:
                amp_cfg = es.cfg['visualization.style.amplitude.channels'][i_channel]
                derived_cmap = _derive_channel_colormap(
                    base_cmap_name, amp_cfg['color'],
                    background_color=amp_cfg['background-color'],
                    radius_degrees=es.cfg['visualization.style.spectrogram.match-channel-color-radius'])
                matplotlib.colormaps.register(derived_cmap, name=cmap_registry_name)
                resolved_spec_channels[i_channel] = {'color-map': cmap_registry_name}
            else:
                resolved_spec_channels[i_channel] = {'color-map': base_cmap_name}

    es.cfg['visualization.style.spectrogram.channels'] = resolved_spec_channels


es.add_event_listener('config.updated', _on_config_updated)
