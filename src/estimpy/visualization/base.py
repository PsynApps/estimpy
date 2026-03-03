"""Base visualization classes for static image rendering.

Contains the Visualization class (matplotlib figure construction for static images),
supporting enums, and module-level convenience functions (show_image, set_optimal_nfft).
"""

import enum
import math
import typing

import estimpy as es
import matplotlib
import matplotlib.gridspec
import matplotlib.patheffects
import matplotlib.pyplot
import numpy as np

# DPI for interactive display — high enough for accurate font rendering at screen resolution
_DISPLAY_DPI = 100


class AxisScaleText(enum.Enum):
    BOTTOM = {
        'va': 'bottom',
        'xy': (0, 0),
        'xytext': (
            es.cfg['visualization.style.axes.text-padding'],
            es.cfg['visualization.style.axes.text-padding'])
    }
    TOP = {
        'va': 'top',
        'xy': (0, 0.99),
        'xytext': (
            es.cfg['visualization.style.axes.text-padding'],
            -es.cfg['visualization.style.axes.text-padding'])
    }


class AxisTypes(enum.StrEnum):
    AMPLITUDE = 'amplitude',
    AMPLITUDE_SCRUB = 'amplitude_scrub',
    CONTROLS = 'controls',
    TITLE = 'title'
    SPECTROGRAM = 'spectrogram'


class VisualizationMode(enum.IntEnum):
    DISPLAY = 0,
    EXPORT = 1


class Visualization:
    def __init__(self, es_audio: es.audio.Audio = None, mode: VisualizationMode = VisualizationMode.DISPLAY):
        self._es_audio = es_audio
        self._envelopes = {}
        self._mode = mode
        self._spectrogram = None
        self._handles = {}

        self._initialize_handles()

        # Store text border width to allow proper rescaling when figure is resized
        self._text_border_width = es.cfg['visualization.style.font.text.border-width']

    @property
    def es_audio(self):
        return self._es_audio

    @property
    def _channel_layout(self):
        """Display order and inversion for each channel: list of (channel_id, invert)."""
        if es.cfg['visualization.triphase'] and self.es_audio.channels == 3:
            return [(0, False), (1, True), (2, False)]
        elif self.es_audio.channels >= 2:
            return [(0, False), (1, True)]
        else:
            return [(0, False)]

    @property
    def _scrub_channel_layout(self):
        """Channel layout for scrub panels: always shows original stereo channels (no triphase)."""
        if self.es_audio.channels >= 2:
            return [(0, False), (1, True)]
        else:
            return [(0, False)]

    @property
    def _layout_ratio_key(self):
        """Config key suffix for height ratios."""
        if es.cfg['visualization.triphase'] and self.es_audio.channels == 3:
            return 'triphase'
        elif self.es_audio.channels >= 2:
            return 'stereo'
        else:
            return 'mono'

    @property
    def peak_envelope(self) -> es.analysis.Envelope:
        if es.analysis.EnvelopeModes.PEAK not in self._envelopes:
            self._envelopes[es.analysis.EnvelopeModes.PEAK] = es.analysis.peak_envelope(
                es_audio=self.es_audio, padding=1)

        return self._envelopes[es.analysis.EnvelopeModes.PEAK]

    @property
    def spectrogram(self) -> es.analysis.Spectrogram:
        if self._spectrogram is None:
            self._spectrogram = es.analysis.spectrogram(es_audio=self.es_audio)

        return self._spectrogram

    @property
    def rms_envelope(self) -> es.analysis.Envelope:
        if es.analysis.EnvelopeModes.RMS not in self._envelopes:
            self._envelopes[es.analysis.EnvelopeModes.RMS] = es.analysis.rms_envelope(
                es_audio=self.es_audio, padding=1)

        return self._envelopes[es.analysis.EnvelopeModes.RMS]

    def i_amplitude(self, t_i):
        return math.floor(
            t_i / self.peak_envelope.times[len(self.peak_envelope.times) - 1] * (len(self.peak_envelope.times) - 1))

    def i_spectrogram(self, t_i):
        return math.floor(
            t_i / self.spectrogram.times[len(self.spectrogram.times) - 1] * (len(self.spectrogram.times) - 1))

    def load(self, es_audio: es.audio.Audio):
        if es_audio is None:
            return

        self._es_audio = es_audio
        self._envelopes = {}
        self._spectrogram = None

        # Preserve the figure while removing all other elements and handles
        figure = self._handles['figure']
        figure.clf()
        self._initialize_handles()
        self._handles['figure'] = figure

        self._handles['figure'].canvas.manager.window.setWindowTitle(self.es_audio.get_string())

        # Regenerate the contents of the figure
        self._make_figure_subplots()

        self._handles['figure'].canvas.draw()

    def make_figure(self) -> matplotlib.pyplot.Figure:
        self._initialize_handles()

        # Use hardcoded size and dpi to ensure relative scaling of fonts, lines, ticks, etc. is correct
        self._handles['figure'] = matplotlib.pyplot.figure(num=1, clear=True)
        self._handles['figure'].set_dpi(_DISPLAY_DPI)
        self._handles['figure'].set_size_inches(es.cfg['visualization.image.display.width'] / _DISPLAY_DPI,
                                                es.cfg['visualization.image.display.height'] / _DISPLAY_DPI)

        self._handles['figure'].canvas.manager.window.setWindowTitle(self.es_audio.get_string())
        self._make_figure_subplots()

        self._add_time_text()

        return self._handles['figure']

    def resize_figure(self, width=None, height=None, dpi=None) -> typing.Tuple[float, float] | None:
        if self._handles['figure'] is None:
            return

        current_width_inches, current_height_inches = self._handles['figure'].get_size_inches()
        current_dpi = self._handles['figure'].get_dpi()
        current_width = current_width_inches * current_dpi
        current_height = current_height_inches * current_dpi

        dpi = current_dpi if dpi is None else dpi
        width = current_width if width is None else width
        height = current_height if height is None else height

        width_scale_factor = width / current_width * current_dpi / dpi
        height_scale_factor = height / current_height * current_dpi / dpi

        # Update text border width to use for path effects
        self._text_border_width = self._text_border_width * current_dpi / dpi

        for text_element in self._handles['text']:
            text_element.set_fontsize(text_element.get_fontsize() * height_scale_factor)

            # Rescale text path effects
            if len(text_element.get_path_effects()) > 0:
                self._set_text_path_effects(text_element)

        for i_axis in self._handles['axes']:
            self._handles['axes'][i_axis].tick_params(
                length=es.cfg['visualization.style.axes.tick-length'] * width_scale_factor,
                width=es.cfg['visualization.style.axes.tick-width'] * height_scale_factor)

        self._handles['figure'].set_size_inches(width / dpi, height / dpi)
        self._handles['figure'].set_dpi(dpi)

        return width_scale_factor, height_scale_factor

    def show_figure(self):
        if self._handles['figure'] is None:
            self.make_figure()

        matplotlib.pyplot.show()

    def _add_amplitude_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec, invert: bool = False):
        if self._handles['figure'] is None:
            return

        axes_style_cfg = self._get_amplitude_style_cfg(channel_id)

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=channel_id)] = ax
        self._format_amplitude_axes(ax=ax, channel_id=channel_id, invert=invert)

        ax.set_facecolor(axes_style_cfg['background-color'])

        ax.fill(self.peak_envelope.times, self.peak_envelope.envelope_data[channel_id, :],
                color=axes_style_cfg['base-color'])

        if es.cfg['visualization.style.amplitude.show-rms']:
            ax.fill(self.rms_envelope.times, self.rms_envelope.envelope_data[channel_id, :],
                    color=axes_style_cfg['rms-color'])

    def _add_figure_subplots(self, gridspec: matplotlib.gridspec.GridSpec) -> int:
        i_subplot = 0

        # Title
        if self._title_enabled(mode=self._mode):
            self._add_title_subplot(gridspec=gridspec[i_subplot])

            i_subplot += 1

        for channel_id, invert in self._channel_layout:
            if invert:
                self._add_amplitude_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot], invert=True)
                i_subplot += 1
                self._add_spectrogram_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot], invert=True)
                i_subplot += 1
            else:
                self._add_spectrogram_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot])
                i_subplot += 1
                self._add_amplitude_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot])
                i_subplot += 1

        return i_subplot

    def _add_time_text(self):
        if self._handles['figure'] is None:
            return

        time_string = self._get_time_text() if self._time_enabled(mode=self._mode) else ''
        position_top = (self._time_position(mode=self._mode) == 'top')
        # Add the time text to the figure
        self._handles['time'] = self._handles['figure'].text(
            x=1, y=1 if position_top else 0, s=time_string,
            ha='right', va='top' if position_top else 'bottom',
            fontsize=es.cfg['visualization.style.time.font-size'],
            fontproperties=es.cfg['visualization.style.font.text.mpl-fontproperties'],
            color=es.cfg['visualization.style.axes.color'])

        # Set text path effects
        self._set_text_path_effects(self._handles['time'])

        # Add the time text handle to the list of text handles
        self._handles['text'].append(self._handles['time'])

    def _add_spectrogram_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec, invert: bool = False):
        if self._handles['figure'] is None:
            return

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)] = ax
        self._format_spectrogram_axes(ax=ax, invert=invert)

        axes_style_cfg = self._get_spectrogram_style_cfg(channel_id)

        ax.imshow(self.spectrogram.spectrogram_data[channel_id, :, :], aspect='auto', origin='lower',
                  cmap=axes_style_cfg['color-map'],
                  extent=[self.spectrogram.times.min(), self.spectrogram.times.max(),
                          self.spectrogram.frequency_min, self.spectrogram.frequency_max],
                  vmin=-es.cfg['visualization.style.spectrogram.dynamic-range'], vmax=0)

    def _add_title_subplot(self, gridspec: matplotlib.gridspec.GridSpec):
        if self._handles['figure'] is None:
            return

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][AxisTypes.TITLE] = ax

        title_text_handle = ax.annotate(self.es_audio.get_string(), xy=(0.5, 0.5), xycoords='axes fraction',
                                        ha='center', va='center',
                                        fontsize=es.cfg['visualization.style.title.font-size'],
                                        fontproperties=es.cfg['visualization.style.font.text.mpl-fontproperties'],
                                        color=es.cfg['visualization.style.title.color'])

        title_text_extent = title_text_handle.get_window_extent()
        title_image_text_width = title_text_extent.x1 - title_text_extent.x0
        if title_image_text_width > es.cfg['visualization.style.title.max-width']:
            title_text_font_size = math.floor(
                es.cfg['visualization.style.title.max-width'] / title_image_text_width
                * es.cfg['visualization.style.title.font-size'])
            title_text_handle.set_fontsize(title_text_font_size)

        ax.set_facecolor(es.cfg['visualization.style.title.background-color'])
        self._handles['text'].append(title_text_handle)
        self._set_text_path_effects(title_text_handle)

    def _format_spectrogram_axes(self, ax, invert=False):
        ax.set_facecolor('black')
        ax.xaxis.set_visible(False)
        ax.set_xlim([0, self.es_audio.length])
        ax.set_ylim([self.spectrogram.frequency_min, self.spectrogram.frequency_max])

        if es.cfg['visualization.style.spectrogram.axes.enabled']:
            spectrogram_yticks = self._get_spectrogram_yticks(self.spectrogram.frequency_max)
            ax.tick_params(axis='y', direction='in',
                           length=es.cfg['visualization.style.axes.tick-length'],
                           width=es.cfg['visualization.style.axes.tick-width'],
                           colors=es.cfg['visualization.style.axes.color'])
            ax.set_yticks(ticks=spectrogram_yticks)
            _mpl_fp = es.cfg['visualization.style.font.text.mpl-fontproperties']
            for label in ax.get_yticklabels():
                label.set_fontproperties(_mpl_fp)

            if not invert:
                axis_label_data_min = AxisScaleText.BOTTOM.value
                axis_label_data_max = AxisScaleText.TOP.value
            else:
                axis_label_data_min = AxisScaleText.TOP.value
                axis_label_data_max = AxisScaleText.BOTTOM.value
            axes_text = [
                ax.annotate(
                    text=self._get_spectrogram_scale_text(self.spectrogram.frequency_min),
                    xy=axis_label_data_min['xy'], xycoords='axes fraction', va=axis_label_data_min['va'],
                    xytext=axis_label_data_min['xytext'], textcoords='offset points',
                    fontsize=es.cfg['visualization.style.axes.font-size'],
                    fontproperties=_mpl_fp,
                    color=es.cfg['visualization.style.axes.color']),
                ax.annotate(
                    text=self._get_spectrogram_scale_text(self.spectrogram.frequency_max),
                    xy=axis_label_data_max['xy'], xycoords='axes fraction', va=axis_label_data_max['va'],
                    xytext=axis_label_data_max['xytext'], textcoords='offset points',
                    fontsize=es.cfg['visualization.style.axes.font-size'],
                    fontproperties=_mpl_fp,
                    color=es.cfg['visualization.style.axes.color'])]

            for text in axes_text:
                # Set text path effects
                self._set_text_path_effects(text)

                # Add to axes text list to support rescaling
                self._handles['text'].append(text)

        if invert:
            ax.invert_yaxis()

    def _get_amplitude_y_max(self, channel_id: int) -> float:
        """Get the amplitude y-axis maximum for a channel.

        The triphase channel -(A+B) can peak at 2.0 (+6 dB) since it sums two channels
        in the analog domain without clipping.
        """
        padding = es.cfg['visualization.style.amplitude.padding']
        if es.cfg['visualization.triphase'] and self.es_audio.channels == 3 and channel_id == 2:
            return 2 * (1 + padding)
        return 1 + padding

    def _format_amplitude_axes(self, ax, channel_id: int = 0, invert: bool = False, hideaxis: bool = False):
        ax.set_facecolor('black')
        ax.xaxis.set_visible(False)
        ax.spines.bottom.set_visible(False)
        ax.spines.top.set_visible(False)
        ax.set_xlim([0, self.es_audio.length])
        # Add padding above envelope
        ax.set_ylim([0, self._get_amplitude_y_max(channel_id)])

        if es.cfg['visualization.style.amplitude.axes.enabled'] and not hideaxis:
            amplitude_yticks = [0]
            ax.tick_params(axis='y', direction='in',
                           length=es.cfg['visualization.style.axes.tick-length'],
                           width=es.cfg['visualization.style.axes.tick-width'],
                           colors=es.cfg['visualization.style.axes.color'])
            ax.set_yticks(ticks=amplitude_yticks)
            _mpl_fp = es.cfg['visualization.style.font.text.mpl-fontproperties']
            for label in ax.get_yticklabels():
                label.set_fontproperties(_mpl_fp)

            if not invert:
                axis_label_data = AxisScaleText.TOP.value
            else:
                axis_label_data = AxisScaleText.BOTTOM.value

            amp_label = '+6 dB' if self._get_amplitude_y_max(channel_id) > 1.5 else '0 dB'
            axes_text = ax.annotate(
                text=amp_label,
                xy=axis_label_data['xy'], xycoords='axes fraction',
                xytext=axis_label_data['xytext'], textcoords='offset points', va=axis_label_data['va'],
                fontsize=es.cfg['visualization.style.axes.font-size'],
                fontproperties=_mpl_fp,
                color=es.cfg['visualization.style.axes.color'])

            # Set text path effects
            self._set_text_path_effects(axes_text)

            # Add to axes text list to support rescaling
            self._handles['text'].append(axes_text)

        if invert:
            ax.invert_yaxis()

    def _get_gridspec_params(self):
        gridspec_params = {
            'ncols': 1,
            'nrows': 0,
            'height_ratios': []
        }

        if self._title_enabled(mode=self._mode):
            gridspec_params['height_ratios'].append(es.cfg['visualization.style.subplot-height-ratios.title'])

        ratio_key = self._layout_ratio_key
        spec_ratio = es.cfg[f'visualization.style.subplot-height-ratios.spectrogram.{ratio_key}']
        amp_ratio = es.cfg[f'visualization.style.subplot-height-ratios.amplitude.{ratio_key}']

        for ch_id, invert in self._channel_layout:
            if invert:
                gridspec_params['height_ratios'] += [amp_ratio, spec_ratio]
            else:
                gridspec_params['height_ratios'] += [spec_ratio, amp_ratio]

        gridspec_params['nrows'] = len(gridspec_params['height_ratios'])

        return gridspec_params

    def _get_time_text(self) -> str:
        return es.utils.seconds_to_string(self.es_audio.length)

    def _initialize_handles(self):
        self._handles = {
            'figure': None,  # type: matplotlib.pyplot.Figure
            'axes': {},  # type: typing.Dict[matplotlib.pyplot.Axes]
            'text': [],  # type: typing.List[matplotlib.pyplot.Text]
            'time': None,  # type: matplotlib.pyplot.Text
        }

    def _make_figure_subplots(self):
        gridspec_params = self._get_gridspec_params()

        # Generate the gridspec for the figure
        gridspec = matplotlib.gridspec.GridSpec(ncols=gridspec_params['ncols'],
                                                nrows=gridspec_params['nrows'],
                                                height_ratios=gridspec_params['height_ratios'])

        self._add_figure_subplots(gridspec=gridspec)

        matplotlib.pyplot.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)

    def _set_text_path_effects(self, text_handle):
        if hasattr(text_handle, 'set_path_effects') and callable(getattr(text_handle, 'set_path_effects')):
            text_handle.set_path_effects([
                matplotlib.patheffects.withStroke(
                    linewidth=self._text_border_width,
                    foreground=es.cfg['visualization.style.font.text.border-color'])
            ])

    @classmethod
    def _get_amplitude_style_cfg(cls, channel_id: int) -> typing.Dict:
        return es.cfg['visualization.style.amplitude.channels'][channel_id] \
            if channel_id < len(es.cfg['visualization.style.amplitude.channels']) else \
            es.cfg['visualization.style.amplitude.channels'][0]

    @classmethod
    def _get_axis_handle_id(cls, type: AxisTypes, channel: int = None):
        return f'{type}_{channel}' if channel is not None else f'{type}'

    @classmethod
    def _get_spectrogram_scale_text(cls, frequency_max: float) -> str:
        if frequency_max < 1000:
            return f'{str(frequency_max)} Hz'
        else:
            frequency_max /= 1000
            frequency_max = int(frequency_max) if frequency_max == int(frequency_max) else round(frequency_max, 1)
            return f'{frequency_max} kHz'

    @classmethod
    def _get_spectrogram_style_cfg(cls, channel_id: int) -> typing.Dict:
        return es.cfg['visualization.style.spectrogram.channels'][channel_id] \
            if channel_id < len(es.cfg['visualization.style.spectrogram.channels']) else \
            es.cfg['visualization.style.spectrogram.channels'][0]

    @classmethod
    def _get_spectrogram_yticks(cls, frequency_max: float):
        if frequency_max < 1000:
            return range(0, frequency_max, 250)
        elif frequency_max < 2000:
            return range(0, frequency_max, 500)
        elif frequency_max < 10000:
            return range(0, frequency_max, 1000)
        elif frequency_max < 20000:
            return range(0, frequency_max, 2500)
        else:
            return range(0, frequency_max, 5000)

    @classmethod
    def _time_enabled(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> bool:
        return es.cfg['visualization.image.export.time.enabled'] if mode is VisualizationMode.EXPORT else \
            es.cfg['visualization.image.display.time.enabled']

    @classmethod
    def _time_position(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> str:
        return es.cfg['visualization.image.export.time.position'] if mode is VisualizationMode.EXPORT else \
            es.cfg['visualization.image.display.time.position']

    @classmethod
    def _title_enabled(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> bool:
        return es.cfg['visualization.image.export.title.enabled'] if mode is VisualizationMode.EXPORT else \
            es.cfg['visualization.image.display.title.enabled']


def show_image(es_audio: es.audio.Audio):
    set_optimal_nfft(es_audio, figure_height=es.cfg['visualization.image.display.height'],
                     title_enabled=es.cfg['visualization.image.display.title.enabled'])
    with es.utils.Spinner(f'Preparing image visualization... '):
        visualization = Visualization(es_audio=es_audio)

    visualization.show_figure()


def set_optimal_nfft(es_audio: es.audio.Audio, figure_height: float,
                     triphase: bool = None, title_enabled: bool = False,
                     include_scrub: bool = False):
    """Set resolution-aware nfft in config if nfft is auto-determined.

    Performs a coarse frequency estimation and calculates the optimal nfft
    based on the spectrogram panel height for the given output dimensions.
    Skips optimization if the user has explicitly configured nfft.

    :param es_audio: Audio object to estimate frequency content from.
    :param figure_height: Output figure height in pixels.
    :param triphase: Whether triphase mode is active (defaults to config value).
    :param title_enabled: Whether the title panel is shown.
    :param include_scrub: Whether scrub panels are included (video mode).
    """
    # Import here to avoid circular dependency at module load time
    from estimpy.visualization import _calculate_spectrogram_panel_height

    if not es.analysis.nfft_auto:
        return

    if triphase is None:
        triphase = es.cfg['visualization.triphase']

    freq_max = es.cfg['analysis.spectrogram.frequency-max']
    if freq_max is None:
        freq_max = es.analysis.estimate_frequency_max_coarse(
            es_audio.data, es_audio.sample_rate)

    panel_height = _calculate_spectrogram_panel_height(
        figure_height=figure_height,
        n_channels=es_audio.channels,
        triphase=triphase,
        title_enabled=title_enabled,
        include_scrub=include_scrub)

    optimal_nfft = es.analysis.calculate_optimal_nfft(
        sample_rate=es_audio.sample_rate,
        frequency_max=freq_max,
        panel_height=panel_height,
        window_size=es.cfg['analysis.window-size'])

    es.cfg['analysis.spectrogram.nfft'] = optimal_nfft
