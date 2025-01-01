import enum
import math
import typing

import estimpy as es
import functools
import matplotlib
import matplotlib.animation
import matplotlib.patheffects
import matplotlib.pyplot
import matplotlib.widgets

_DPI = 100

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


class PlaybackIcons(enum.StrEnum):
    PLAY = '\u23F5',
    PAUSE = '\u23F8',
    STOP = '\u23F9',
    SKIP_BACK = '\u23EA',
    SKIP_FORWARD = '\u23E9'
    PREVIOUS_FILE = '\u23EE',
    NEXT_FILE = '\u23ED',
    VOLUME_UP = '\u2795',
    VOLUME_DOWN = '\u2796',
    MUTED = '\U0001F507',
    UNMUTED = '\U0001F50A'


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
        self._handles['figure'].set_dpi(_DPI)
        self._handles['figure'].set_size_inches(es.cfg['visualization.image.display.width'] / _DPI,
                                                es.cfg['visualization.image.display.height'] / _DPI)

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
        self._format_amplitude_axes(ax=ax, invert=invert)

        ax.set_facecolor(axes_style_cfg['background-color'])

        ax.fill(self.peak_envelope.times, self.peak_envelope.envelope_data[channel_id, :],
                color=axes_style_cfg['peak-color'])

        if es.cfg['visualization.style.amplitude.show-rms']:
            ax.fill(self.rms_envelope.times, self.rms_envelope.envelope_data[channel_id, :],
                    color=axes_style_cfg['rms-color'])

    def _add_figure_subplots(self, gridspec: matplotlib.gridspec.GridSpec) -> int:
        i_subplot = 0

        # Title
        if self._title_enabled(mode=self._mode):
            self._add_title_subplot(gridspec=gridspec[i_subplot])

            i_subplot += 1

        for channel_id in range(self.es_audio.channels):
            if channel_id == 1 and self.es_audio.channels == 2:
                # Special case for the right channel of stereo audio where the amplitude and spectrogram axes
                # should be shown in opposite order and inverted
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
        # Add the time text to the figure
        self._handles['time'] = self._handles['figure'].text(
            x=1, y=0, s=time_string, ha='right', va='bottom',
            fontsize=es.cfg['visualization.style.time.font-size'],
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
                    color=es.cfg['visualization.style.axes.color']),
                ax.annotate(
                    text=self._get_spectrogram_scale_text(self.spectrogram.frequency_max),
                    xy=axis_label_data_max['xy'], xycoords='axes fraction', va=axis_label_data_max['va'],
                    xytext=axis_label_data_max['xytext'], textcoords='offset points',
                    fontsize=es.cfg['visualization.style.axes.font-size'],
                    color=es.cfg['visualization.style.axes.color'])]

            for text in axes_text:
                # Set text path effects
                self._set_text_path_effects(text)

                # Add to axes text list to support rescaling
                self._handles['text'].append(text)

        if invert:
            ax.invert_yaxis()

    def _format_amplitude_axes(self, ax, invert: bool = False, hideaxis: bool = False):
        ax.set_facecolor('black')
        ax.spines.bottom.set_visible(False)
        ax.spines.top.set_visible(False)
        ax.set_xlim([0, self.es_audio.length])
        # Add padding above envelope
        ax.set_ylim([0, 1 + es.cfg['visualization.style.amplitude.padding']])

        if es.cfg['visualization.style.amplitude.axes.enabled'] and not hideaxis:
            amplitude_yticks = [0]
            ax.tick_params(axis='y', direction='in',
                           length=es.cfg['visualization.style.axes.tick-length'],
                           width=es.cfg['visualization.style.axes.tick-width'],
                           colors=es.cfg['visualization.style.axes.color'])
            ax.set_yticks(ticks=amplitude_yticks)

            if not invert:
                axis_label_data = AxisScaleText.TOP.value
            else:
                axis_label_data = AxisScaleText.BOTTOM.value

            axes_text = ax.annotate(
                text='0 dB',
                xy=axis_label_data['xy'], xycoords='axes fraction',
                xytext=axis_label_data['xytext'], textcoords='offset points', va=axis_label_data['va'],
                fontsize=es.cfg['visualization.style.axes.font-size'],
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

        if self.es_audio.channels == 1:
            # Mono
            gridspec_params['height_ratios'] += [es.cfg['visualization.style.subplot-height-ratios.spectrogram.mono'],
                                                 es.cfg['visualization.style.subplot-height-ratios.amplitude.mono']]
        elif self.es_audio.channels == 2:
            # Stereo
            gridspec_params['height_ratios'] += [
                es.cfg['visualization.style.subplot-height-ratios.spectrogram.stereo'],
                es.cfg['visualization.style.subplot-height-ratios.amplitude.stereo'],
                es.cfg['visualization.style.subplot-height-ratios.amplitude.stereo'],
                es.cfg['visualization.style.subplot-height-ratios.spectrogram.stereo']]
        else:
            # Multichannel
            # TODO need a generalized solution to calculate ratios based upon number of channels (including stereo)
            raise Exception('Multichannel audio is not yet supported')

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

    def _remove_elements(self, handle_list):
        for handle in handle_list:
            if isinstance(handle, list):
                self._remove_elements(handle)
            else:
                handle.remove()

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
    def _title_enabled(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> bool:
        return es.cfg['visualization.image.export.title.enabled'] if mode is VisualizationMode.EXPORT else \
            es.cfg['visualization.image.display.title.enabled']


class VideoVisualization(Visualization):
    def __init__(self, es_audio: es.audio.Audio = None, fps: float = None, frames: range = None):
        super().__init__(es_audio=es_audio)

        self._animation = None  # type: matplotlib.animation.FuncAnimation | None
        self._fps = es.cfg['visualization.video.export.fps'] if fps is None else fps
        self._frames = range(math.floor(es_audio.length * self.fps)) if frames is None else frames
        self._frame = 0

        # Length of video windows
        # Padding ensures there sufficient data to fill the window without glitches (does not need to be configurable)
        self._window_padding_factor = 1.1
        self._window_length = es.cfg['visualization.video.export.window-length']

        self.__amplitude_window_length = None
        self.__spectrogram_window_length = None


    @property
    def animation(self) -> matplotlib.animation.FuncAnimation | None:
        if self._animation is None:
            self._set_animation()

        return self._animation

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frames(self) -> range:
        return self._frames

    @property
    def _amplitude_window_length(self):
        if self.__amplitude_window_length is None:
            self.__amplitude_window_length = self.i_amplitude(
                self._window_padding_factor * self._window_length)

        return self.__amplitude_window_length

    @property
    def _spectrogram_window_length(self):
        if self.__spectrogram_window_length is None:
            self.__spectrogram_window_length = self.i_spectrogram(
                self._window_padding_factor * self._window_length)

        return self.__spectrogram_window_length

    def load(self, es_audio: es.audio.Audio):
        if es_audio is None:
            return

        super().load(es_audio=es_audio)

        self._animation = None
        self._frames = range(math.floor(es_audio.length * self.fps))

    def make_figure(self):
        super().make_figure()
        self.make_frame(0)

    def make_frame(self, frame):
        if self._handles['figure'] is None:
            return

        self._frame = frame
        t = self._frame_to_time(frame)

        self._remove_elements(self._handles['video_frame'])
        self._handles['video_frame'].clear()

        for position_line in self._handles['position_lines']:
            position_line.set_xdata([t])

        axes_xlim = self._get_window_range(
            t=t,
            total_length=self.es_audio.length,
            window_length=self._window_length)

        i_amplitude_min, i_amplitude_max = self._get_window_range(
            t=self.i_amplitude(t),
            total_length=len(self.peak_envelope.times) - 1,
            window_length=self._amplitude_window_length,
            round_bounds=True)

        # Update the amplitude
        for channel_id in range(self.es_audio.channels):
            axes_style_cfg = self._get_amplitude_style_cfg(channel_id)

            axes_key = self._get_axis_handle_id(type=AxisTypes.AMPLITUDE, channel=channel_id)

            self._handles['axes'][axes_key].set_xlim(axes_xlim)
            self._handles['video_frame'].append(
                self._handles['axes'][axes_key].fill(
                    self.peak_envelope.times[i_amplitude_min:i_amplitude_max],
                    es.analysis.Envelope.pad_envelope_data(
                        self.peak_envelope.envelope_data[channel_id, (i_amplitude_min + 1):(i_amplitude_max - 1)]),
                    color=axes_style_cfg['peak-color']))

            if es.cfg['visualization.style.amplitude.show-rms']:
                self._handles['video_frame'].append(
                    self._handles['axes'][axes_key].fill(
                        self.rms_envelope.times[i_amplitude_min:i_amplitude_max],
                        es.analysis.Envelope.pad_envelope_data(
                            self.rms_envelope.envelope_data[channel_id, (i_amplitude_min + 1):(i_amplitude_max - 1)]),
                        color=axes_style_cfg['rms-color']))

        i_spectrogram_min, i_spectrogram_max = self._get_window_range(
            t=self.i_spectrogram(t),
            total_length=len(self.spectrogram.times) - 1,
            window_length=self._spectrogram_window_length,
            round_bounds=True)

        for channel_id in range(self.es_audio.channels):
            axes_style_cfg = self._get_spectrogram_style_cfg(channel_id)

            axes_key = self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)

            self._handles['axes'][axes_key].set_xlim(axes_xlim)
            self._handles['video_frame'].append(
                self._handles['axes'][axes_key].imshow(
                    self.spectrogram.spectrogram_data[channel_id, :, i_spectrogram_min:i_spectrogram_max],
                    aspect='auto', origin='lower',
                    cmap=axes_style_cfg['color-map'],
                    extent=[self.spectrogram.times[i_spectrogram_min],
                            self.spectrogram.times[i_spectrogram_max],
                            self.spectrogram.frequency_min,
                            self.spectrogram.frequency_max],
                    vmin=-es.cfg['visualization.style.spectrogram.dynamic-range'], vmax=0))

        self._update_time_text()

        return self._handles['figure']

    def resize_figure(self, width=None, height=None, dpi=None) -> typing.Tuple[float, float] | None:
        if self._handles['figure'] is None:
            return

        width_scale_factor, height_scale_factor = super().resize_figure(width=width, height=height, dpi=dpi)

        for position_line in self._handles['position_lines']:
            position_line.set_linewidth(position_line.get_linewidth() * width_scale_factor)

        return width_scale_factor, height_scale_factor

    def _add_amplitude_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec,
                               invert: bool = False, scrub: bool = False):
        if self._handles['figure'] is None:
            return

        axis_type = AxisTypes.AMPLITUDE_SCRUB if scrub else AxisTypes.AMPLITUDE
        axes_style_cfg = self._get_amplitude_style_cfg(channel_id)

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=axis_type, channel=channel_id)] = ax
        self._format_amplitude_axes(ax=ax, invert=invert, hideaxis=scrub)

        ax.set_facecolor(axes_style_cfg['background-color'])

        # If rendering a video, only render the amplitude envelope here if making a scrub subplot
        # since otherwise it the contents will change with each frame
        if scrub:
            ax.set_xlim(self.peak_envelope.times[0], self.peak_envelope.times[len(self.peak_envelope.times) - 1])
            ax.fill(self.peak_envelope.times, self.peak_envelope.envelope_data[channel_id, :],
                    color=axes_style_cfg['peak-color'])

            if es.cfg['visualization.style.amplitude.show-rms']:
                ax.fill(self.rms_envelope.times, self.rms_envelope.envelope_data[channel_id, :],
                        color=axes_style_cfg['rms-color'])

        self._handles['position_lines'].append(
            ax.axvline(x=0, lw=1, color=es.cfg['visualization.style.video.position-line-color']))

    def _add_figure_subplots(self, gridspec: matplotlib.gridspec.GridSpec) -> int:
        i_subplot = super()._add_figure_subplots(gridspec=gridspec)

        # Additional amplitude subplots if rendering a video to show envelopes for full file for scrubbing purposes
        for channel_id in range(self.es_audio.channels):
            self._add_amplitude_subplot(channel_id=channel_id, gridspec=gridspec[i_subplot],
                                        invert=(channel_id == 1 and self.es_audio.channels == 2), scrub=True)
            i_subplot += 1

        return i_subplot

    def _add_spectrogram_subplot(self, channel_id: int, gridspec: matplotlib.gridspec.GridSpec, invert: bool = False):
        if self._handles['figure'] is None:
            return

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.SPECTROGRAM, channel=channel_id)] = ax
        self._format_spectrogram_axes(ax=ax, invert=invert)

        # If rendering a video, don't bother rendering the spectrogram since it will change with each frame
        self._handles['position_lines'].append(
            ax.axvline(x=0, lw=1, color=es.cfg['visualization.style.video.position-line-color']))

    def _frame_to_time(self, frame):
        return frame / self.fps

    def _get_gridspec_params(self):
        gridspec_params = super()._get_gridspec_params()

        if self.es_audio.channels == 1:
            # If the figure is for a video, add 1 more amplitude panel with half the normal height at the bottom
            gridspec_params['height_ratios'].append(
                es.cfg['visualization.style.subplot-height-ratios.amplitude.mono'] / 2)
        elif self.es_audio.channels == 2:
            # If the figure is for a video, add 2 more amplitude panels with half the normal height at the bottom
            gridspec_params['height_ratios'].append(
                es.cfg['visualization.style.subplot-height-ratios.amplitude.stereo'] / 2)
            gridspec_params['height_ratios'].append(
                es.cfg['visualization.style.subplot-height-ratios.amplitude.stereo'] / 2)
        else:
            # Multichannel
            raise Exception('Multichannel audio is not yet supported')

        gridspec_params['nrows'] = len(gridspec_params['height_ratios'])

        return gridspec_params

    def _get_time_text(self) -> str:
        return es.utils.seconds_to_string(self._frame_to_time(self._frame)) + ' / ' \
            + es.utils.seconds_to_string(self.es_audio.length)

    def _get_window_range(self, t, total_length, window_length, round_bounds: bool = False):
        # Calculate half the window length
        half_window_length = window_length / 2

        # If rounding the bounds, floor the half width
        if round_bounds:
            half_window_length = math.floor(half_window_length)

        # Ensure the min is not less than 0 or greater than one full window length from the end of the data
        window_min = max(0, min(total_length - window_length, t - half_window_length))
        # Ensure the max doesn't run past the end of the data
        window_max = max(min(total_length, window_length), min(total_length, t + half_window_length))

        return window_min, window_max

    def _initialize_handles(self):
        super()._initialize_handles()

        self._handles['position_lines'] = []
        self._handles['video_frame'] = []

    def _set_animation(self):
        if self._handles['figure'] is None:
            return

        self._animation = matplotlib.animation.FuncAnimation(fig=self._handles['figure'], func=self.make_frame,
                                                             frames=self.frames, repeat=False, cache_frame_data=False,
                                                             interval=1)

    def _time_to_frame(self, time):
        return math.floor(time * self.fps)

    def _update_time_text(self):
        if self._handles['time'] is None:
            return

        if self._time_enabled():
            self._handles['time'].set_text(self._get_time_text())
        else:
            self._handles['time'].set_text('')

    @classmethod
    def _time_enabled(cls, mode: VisualizationMode = VisualizationMode.EXPORT) -> bool:
        return es.cfg['visualization.video.export.time.enabled']

    @classmethod
    def _title_enabled(cls, mode: VisualizationMode = VisualizationMode.EXPORT) -> bool:
        return es.cfg['visualization.video.export.title.enabled']


class VideoPlayerVisualization(VideoVisualization):
    def __init__(self, player: es.player.Player = None):
        self._player = player  # type: es.player.Player()
        es_audio = self._player.get_es_audio()

        super().__init__(es_audio=es_audio)

        self._frame = 0  # type: int

        self._window_length = es.cfg['visualization.video.display.window-length']

        # Used to prevent loops when ui is being redrawn and updating values of controls which would trigger events
        self.__ui_updating = False  # type: bool

    @property
    def frame(self) -> int:
        return self._frame

    @property
    def player(self) -> es.player.Player:
        return self._player

    def load(self, es_audio: es.audio.Audio):
        if es_audio is None:
            return

        super().load(es_audio=es_audio)

    def make_figure(self):
        super().make_figure()

        # Hide the toolbar
        self._handles['figure'].canvas.manager.toolbar.setVisible(False)

        self._handles['figure'].canvas.mpl_connect('button_press_event', self._on_button_press)
        self._handles['figure'].canvas.mpl_connect('key_press_event', self._on_key_press)
        self._handles['figure'].canvas.mpl_connect('motion_notify_event', self._on_motion_notify)

    def make_frame(self, frame: int = 0):
        if self._handles['figure'] is None:
            return

        # If playing, ignore the requested frame and set the frame to the time of the playing audio
        if self.player.is_playing():
            audio_time = None
            if es.player.audio.is_playing():
                audio_time = es.player.audio.get_time() + es.cfg['player.video-render-latency']
            else:
                # The animation should only be playing with the audio not playing when the file has completed playback
                audio_time = 0
                self.player.stop()
            self._frame = self._time_to_frame(audio_time)
        else:
            self._frame = frame

        super().make_frame(self._frame)

        self._handles['clock'].set_text(self._get_time_text())

        # Update the volume sliders to reflect the true playback volume without triggering the on_changed event
        for channel in range(self.es_audio.channels):
            ui_updating = self._ui_updating(True)
            self._handles['volume_slider'][channel].set_val(es.player.audio.get_volume(channel))
            self._ui_updating(ui_updating)

        return self._handles['figure']

    def mute(self, channel: int = None):
        button_id = None

        if channel is None:
            # Mute master
            button_id = 'mute-unmute-master'
        else:
            # Mute channel
            button_id = f'mute-unmute-{channel}'

        self._set_button_label_text(self._handles['buttons'][button_id], PlaybackIcons.MUTED)
        self._set_button_active(self._handles['buttons'][button_id])

    def pause(self):
        if self.animation is not None:
            self.animation.pause()

        self._set_button_label_text(self._handles['buttons']['play-pause'], PlaybackIcons.PLAY)

        self._handles['figure'].canvas.draw()

    def play(self):
        # If trying to play from the end of the file, reset to the beginning
        # if self.time >= self.es_audio.length:
        #    self._time = 0

        if self.animation is None:
            self._set_animation()
        else:
            self.animation.resume()

        self._handles['buttons']['play-pause'].label.set_text(PlaybackIcons.PAUSE)
        self._set_button_inactive(self._handles['buttons']['stop'])

        self._handles['figure'].canvas.draw()

    def set_time(self, time: float):
        self.make_frame(self._time_to_frame(min(max(0, time), self._frame_to_time(len(self.frames) - 1))))
        self._handles['figure'].canvas.draw()

    def set_volume(self, volume: int, channel: int = None):
        if channel is None:
            for channel_id in range(self.es_audio.channels):
                self.set_volume(volume=volume, channel=channel_id)
            return

        volume = volume if volume is not None else self.player.get_channel_volume(channel)
        volume = max(0, min(100, round(volume)))

        ui_updating = self._ui_updating(True)
        self._handles['volume_slider'][channel].set_val(volume)
        self._ui_updating(ui_updating)

        self._handles['figure'].canvas.draw()

    def show_figure(self):
        if es.cfg['player.autoplay']:
            self._set_animation()

        super().show_figure()

    def stop(self):
        if self.animation is not None:
            self.animation.pause()

        self.set_time(0)

        self._set_button_label_text(self._handles['buttons']['play-pause'], PlaybackIcons.PLAY)
        self._set_button_active(self._handles['buttons']['stop'])

        self._handles['figure'].canvas.draw()

    def toggle_full_screen(self):
        manager = matplotlib.pyplot.get_current_fig_manager()
        if self.player.is_full_screen():
            manager.window.showNormal()
        else:
            manager.window.showMaximized()

    def unmute(self, channel: int = None):
        button_id = None

        if channel is None:
            # Unmute master, set volume to all channels to 0 but don't update their individual UI
            button_id = 'mute-unmute-master'
        else:
            # Unmute channel
            button_id = f'mute-unmute-{channel}'

        self._set_button_label_text(self._handles['buttons'][button_id], PlaybackIcons.UNMUTED)
        self._set_button_inactive(self._handles['buttons'][button_id])

    def _add_figure_subplots(self, gridspec: matplotlib.gridspec.GridSpec) -> int:
        i_subplot = super()._add_figure_subplots(gridspec=gridspec)

        self._add_controls_subplot(gridspec=gridspec[i_subplot])
        i_subplot += 1

        return i_subplot

    def _add_controls_subplot(self, gridspec: matplotlib.gridspec.GridSpec):
        if self._handles['figure'] is None:
            return

        ax = self._handles['figure'].add_subplot(gridspec)
        self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.CONTROLS)] = ax

        button_size = 0.04

        # How much wider the figure is than tall
        button_aspect_ratio = \
            es.cfg['visualization.video.display.width'] / es.cfg['visualization.video.display.height']

        # Compensate for aspect ratio to make buttons square
        button_width = button_size / button_aspect_ratio
        button_height = button_size
        button_bottom = 0.015
        button_padding = 0.02

        text_y_18 = 0.5

        buttons = {
            'play-pause': {
                'text': PlaybackIcons.PLAY,
                'left': button_padding
            },
            'stop': {
                'text': PlaybackIcons.STOP,
                'left': 0
            },
            'previous-file': {
                'text': PlaybackIcons.PREVIOUS_FILE,
                'left': button_padding
            },
            'skip-back': {
                'text': PlaybackIcons.SKIP_BACK,
                'left': 0
            },
            'skip-forward': {
                'text': PlaybackIcons.SKIP_FORWARD,
                'left': 0,
                'bottom': 0.02
            },
            'next-file': {
                'text': PlaybackIcons.NEXT_FILE,
                'left': 0
            }
        }

        # Add elements from left to right
        current_left = 0
        for button_id in buttons:
            current_left += buttons[button_id]['left']

            self._handles['buttons'][button_id] = matplotlib.widgets.Button(
                matplotlib.pyplot.axes((
                    current_left,
                    button_bottom,
                    button_width,
                    button_height)),
                buttons[button_id]['text'])

            current_left += button_width

            self._format_button(self._handles['buttons'][button_id])

            event = button_id if 'event' not in buttons[button_id] else buttons[button_id]['event']

            self._handles['buttons'][button_id].on_clicked(functools.partial(self._event_handler, event))

            self._handles['text'].append(self._handles['buttons'][button_id].label)

        # Clock
        current_left += button_padding
        clock_string = self._get_time_text()
        clock_font_size = 22
        self._handles['clock'] = ax.text(
            x=current_left,
            y=0.45,
            s=clock_string,
            transform=ax.transAxes, fontsize=clock_font_size, va='center')
        self._handles['text'].append(self._handles['clock'])

        clock_text_extent = self._handles['clock'].get_window_extent()
        clock_image_text_width = clock_text_extent.x1 - clock_text_extent.x0

        clock_text_max_width_factor = 0.12
        clock_text_max_width = math.floor(clock_text_max_width_factor * es.cfg['visualization.video.display.width'])

        if clock_image_text_width > clock_text_max_width:
            title_text_font_size = math.floor(clock_text_max_width / clock_image_text_width * clock_font_size)
            self._handles['clock'].set_fontsize(title_text_font_size)

        # Add elements from right to left
        slider_width = 4 * button_width

        volume_buttons = {
            'volume-up': {
                'text': PlaybackIcons.VOLUME_UP,
                'left': None,
                'event': 'volume-up',
                'channel': None
            },
            'volume-down': {
                'text': PlaybackIcons.VOLUME_DOWN,
                'left': None,
                'event': 'volume-down',
                'channel': None
            },
            'mute-unmute': {
                'text': PlaybackIcons.UNMUTED,
                'left': None,
                'event': 'mute-unmute',
                'channel': None
            }
        }

        current_left = 1
        for channel_id in range(self.es_audio.channels - 1, 0 - 1, -1):
            current_left -= 2 * button_padding + slider_width

            self._handles['volume_slider'][channel_id] = matplotlib.widgets.Slider(
                ax=matplotlib.pyplot.axes((
                    current_left,
                    button_bottom,
                    slider_width,
                    button_height)),
                label='',
                valmin=0,
                valmax=100,
                valstep=1,
                initcolor=None
            )

            self._handles['volume_slider'][channel_id].set_val(self.player.get_channel_volume(channel_id))
            self._handles['volume_slider'][channel_id].valtext.set_fontsize(18)
            self._handles['text'].append(self._handles['volume_slider'][channel_id].valtext)

            self._handles['volume_slider'][channel_id].on_changed(functools.partial(
                self._event_handler,
                'volume-slider',
                channel=channel_id))

            current_left -= button_padding
            for volume_button_id in volume_buttons:
                button_id = f'{volume_button_id}-{channel_id}'
                current_left -= button_width

                self._handles['buttons'][button_id] = matplotlib.widgets.Button(
                    matplotlib.pyplot.axes((
                        current_left,
                        button_bottom,
                        button_width,
                        button_height)),
                    volume_buttons[volume_button_id]['text'])

                self._format_button(self._handles['buttons'][button_id])

                event = volume_button_id if 'event' not in volume_buttons[volume_button_id] \
                    else volume_buttons[volume_button_id]['event']

                self._handles['buttons'][button_id].on_clicked(functools.partial(
                    self._event_handler,
                    event,
                    channel=channel_id))

                self._handles['text'].append(self._handles['buttons'][button_id].label)

            # The label is approximately the same width as a button padding
            current_left -= 1.5 * button_padding
            self._handles['text'].append(ax.text(
                x=current_left,
                y=text_y_18,
                s=chr(channel_id + 65),
                transform=ax.transAxes, fontsize=22, va='center'))

            # The line is approximately the same width as a button padding
            current_left -= 0.75 * button_padding
            ax.axvline(x=current_left, color='k', lw=0.5)

        # Master volume controls
        current_left -= button_padding
        for volume_button_id in volume_buttons:
            button_id = f'{volume_button_id}-master'
            current_left -= button_width

            self._handles['buttons'][button_id] = matplotlib.widgets.Button(
                matplotlib.pyplot.axes((
                    current_left,
                    button_bottom,
                    button_width,
                    button_height)),
                volume_buttons[volume_button_id]['text'])

            self._format_button(self._handles['buttons'][button_id])

            event = volume_button_id if 'event' not in volume_buttons[volume_button_id] \
                else volume_buttons[volume_button_id]['event']

            self._handles['buttons'][button_id].on_clicked(functools.partial(self._event_handler, event))

            self._handles['text'].append(self._handles['buttons'][button_id].label)

        # The label is approximately the same width as a 2.25 button paddings
        current_left -= 2.25 * button_padding
        self._handles['text'].append(ax.text(
            x=current_left,
            y=text_y_18,
            s='All',
            transform=ax.transAxes, fontsize=22, va='center'))

        # The line is approximately the same width a button padding
        current_left -= 0.75 * button_padding
        ax.axvline(x=current_left, color='k', lw=0.5)

    def _event_handler(self, event, event_data=None, channel=None):
        if event == 'play-pause':
            self.player.toggle_playing()
        elif event == 'stop':
            self.player.stop()
        elif event == 'rewind':
            self.player.set_time(0)
        elif event == 'skip-back':
            self.player.set_time(self.player._time - es.cfg['player.skip-length'])
        elif event == 'skip-forward':
            self.player.set_time(self.player._time + es.cfg['player.skip-length'])
        elif event == 'previous-file':
            self.player.previous_file()
        elif event == 'next-file':
            self.player.next_file()
        elif event == 'volume-down':
            self.player.step_volume(volume_step=-es.cfg['player.volume-step'], channel=channel)
        elif event == 'volume-up':
            self.player.step_volume(volume_step=es.cfg['player.volume-step'], channel=channel)
        elif event == 'volume-slider' and not self._ui_updating():
            self.player.set_volume(volume=event_data, channel=channel)
        elif event == 'mute-unmute':
            self.player.toggle_muted(channel=channel)

    def _format_button(self, button_handle):
        if button_handle:
            button_font_name = es.cfg['visualization.style.font.symbols.properties'].get_family()

            button_handle.label.set_fontname(button_font_name)
            button_handle.label.set_fontsize(16)

    def _get_time_text(self):
        return es.utils.seconds_to_string(self.player.get_time()) + ' / ' \
            + es.utils.seconds_to_string(self.es_audio.length)

    def _get_gridspec_params(self):
        gridspec_params = super()._get_gridspec_params()

        gridspec_params['height_ratios'].append(es.cfg['visualization.style.subplot-height-ratios.controls'])
        gridspec_params['nrows'] = len(gridspec_params['height_ratios'])

        return gridspec_params

    def _initialize_handles(self):
        super()._initialize_handles()

        self._handles['buttons'] = {}
        self._handles['clock'] = None
        self._handles['volume_slider'] = {}  # type: typing.Dict[matplotlib.widgets.Slider]

    def _on_button_press(self, event):
        if event.inaxes is None:
            return

        for axes_handle in self._handles['axes']:
            if self._handles['axes'][axes_handle] == event.inaxes:
                if axes_handle.find(AxisTypes.AMPLITUDE_SCRUB) == -1 and \
                        axes_handle.find(AxisTypes.CONTROLS) == -1:
                    self.player.toggle_playing()
                elif axes_handle.find(AxisTypes.AMPLITUDE_SCRUB) >= 0:
                    self.player.set_time(event.xdata)

    def _on_key_press(self, event):
        if event.key.isspace():
            self._event_handler('play-pause')
        elif event.key == 'down':
            self._event_handler('volume-down')
        elif event.key == 'up':
            self._event_handler('volume-up')
        elif event.key == 'left':
            self._event_handler('skip-backward')
        elif event.key == 'right':
            self._event_handler('skip-forward')
        elif event.key == 'pageup':
            self._event_handler('previous-file')
        elif event.key == 'pagedown':
            self._event_handler('next-file')
        elif event.key == 'home':
            self._event_handler('rewind')
        elif event.key == 'end':
            self.stop()
            matplotlib.pyplot.close(self._handles['figure'])
        elif event.key == 'f' or event.key == 'alt+enter':
            self.toggle_full_screen()

    def _on_motion_notify(self, event):
        if event.inaxes is None or event.button is None:
            return

        for axes_handle in self._handles['axes']:
            if self._handles['axes'][axes_handle] == event.inaxes and axes_handle.find(AxisTypes.AMPLITUDE_SCRUB) != -1:
                self.player.set_time(event.xdata)

    def _set_animation(self):
        if self._handles['figure'] is None:
            return

        self._animation = matplotlib.animation.FuncAnimation(fig=self._handles['figure'], func=self.make_frame,
                                                             repeat=False, cache_frame_data=False)

    def _set_button_active(self, button_handle) -> None:
        if button_handle:
            active_color = 0.95
            button_handle.color = (active_color, active_color, active_color, 1)
            self._handles['figure'].canvas.draw()

    def _set_button_inactive(self, button_handle) -> None:
        if button_handle:
            active_color = 0.85
            button_handle.color = (active_color, active_color, active_color, 1)
            self._handles['figure'].canvas.draw()

    def _set_button_label_text(self, button_handle, label_text: str = None):
        if button_handle:
            button_handle.label.set_text(label_text)
            self._handles['figure'].canvas.draw()

    def _ui_updating(self, ui_updating: bool = None) -> bool:
        # We will want to return the value of _ui_updating *before* potentially updating it to allow nesting
        prev_ui_updating = self.__ui_updating

        if ui_updating is not None:
            self.__ui_updating = ui_updating

        return prev_ui_updating

    def _update_time_text(self):
        if self._handles['figure'] is None or self._handles['time'] is None:
            return

        super()._update_time_text()

        ax_controls = self._handles['axes'][self._get_axis_handle_id(type=AxisTypes.CONTROLS)]

        if ax_controls:
            figure_height = self._handles['figure'].get_window_extent().y1
            controls_height = ax_controls.get_window_extent().y1

            self._handles['time'].set_position((1, 0 + (controls_height / figure_height)))

    @classmethod
    def _time_enabled(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> bool:
        return es.cfg['visualization.video.display.time.enabled']

    @classmethod
    def _title_enabled(cls, mode: VisualizationMode = VisualizationMode.DISPLAY) -> bool:
        return es.cfg['visualization.video.display.title.enabled']


def show_image(es_audio: es.audio.Audio):
    spinner = es.utils.Spinner(f'Preparing image visualization... ')
    visualization = Visualization(es_audio=es_audio)
    spinner.stop()

    visualization.show_figure()


# Helper function to apply alpha just with RGB (i.e. not RGBA)
def _alpha_color(color, bg_color, alpha) -> str:
    rgb = matplotlib.colors.to_rgb(color)
    bg_rgb = matplotlib.colors.to_rgb(bg_color)
    alpha_rgb = [alpha * c1 + (1 - alpha) * c2 for (c1, c2) in zip(rgb, bg_rgb)]
    return '#' + ''.join(f'{i:02X}' for i in [round(255 * x) for x in alpha_rgb])


def _on_config_updated():
    # Configuration

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

    # Font
    # Text
    es.cfg['visualization.style.font.text.properties'] = matplotlib.font_manager.FontProperties(
        family=[item.strip() for item in es.cfg['visualization.style.font.text.family'].split(',')],
        weight=es.cfg['visualization.style.font.text.weight'])
    es.cfg['visualization.style.font.text.file'] = matplotlib.font_manager.findfont(
        es.cfg['visualization.style.font.text.properties'])
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

    # Channel colors
    cfg_prefixes = [
        "visualization.style.amplitude.channels",
        "visualization.style.spectrogram.channels"
    ]

    # Initialize a dictionary to store the maximum channel number for each prefix
    max_channels = {prefix: 0 for prefix in cfg_prefixes}

    # Extract the maximum channel number for each prefix
    for key in es.cfg.keys():
        for prefix in cfg_prefixes:
            if key.startswith(prefix):
                parts = key[len(prefix):].split('.')
                if len(parts) > 1 and parts[1].startswith("ch"):
                    channel_number = int(parts[1][2:])  # Extract and cast to int
                    max_channels[prefix] = max(max_channels[prefix], channel_number)

    # Generate full channel lists (continuous from 1 to max_channels)
    channel_numbers = {prefix: list(range(0, max_channels[prefix] + 1)) for prefix in max_channels}

    es.cfg['visualization.style.amplitude.channels'] = [None] * len(channel_numbers['visualization.style.amplitude.channels'])
    for i_channel in channel_numbers['visualization.style.amplitude.channels']:
        es.cfg['visualization.style.amplitude.channels'][i_channel] = {
            'peak-color': None,
            'rms-color': None,
            'background-color': None
        }

        # If the color of the peak amplitude envelope is not defined, use the color from the first channel
        es.cfg['visualization.style.amplitude.channels'][i_channel]['peak-color'] = \
            es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.peak-color'] if \
                es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.peak-color'] is not None else \
                es.cfg['visualization.style.amplitude.channels.ch0.peak-color']

        # If the color of the rms amplitude envelope is not defined,
        # derive the color from the blending the peak color with white using the alpha level
        es.cfg['visualization.style.amplitude.channels'][i_channel]['rms-color'] = \
            es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.rms-color'] if \
                es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.rms-color'] is not None else \
                _alpha_color(
                    es.cfg['visualization.style.amplitude.channels'][i_channel]['peak-color'], (1, 1, 1),
                    es.cfg['visualization.style.amplitude.rms-alpha'])

        # If the background color of the amplitude panel is not defined,
        # derive the color from the blending the peak color with black using the alpha level
        es.cfg['visualization.style.amplitude.channels'][i_channel]['background-color'] = \
            es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.background-color'] if \
                es.cfg[f'visualization.style.amplitude.channels.ch{i_channel}.background-color'] is not None else \
                _alpha_color(
                    es.cfg['visualization.style.amplitude.channels'][i_channel]['peak-color'], (0, 0, 0),
                    es.cfg['visualization.style.amplitude.background-alpha'])

    es.cfg['visualization.style.spectrogram.channels'] = [None] * len(channel_numbers['visualization.style.spectrogram.channels'])
    for i_channel in channel_numbers['visualization.style.spectrogram.channels']:
        es.cfg['visualization.style.spectrogram.channels'][i_channel] = {
            'color-map': None
        }

        # If the color map for the spectrogram of the channel is not defined, use the color map from the first channel
        es.cfg['visualization.style.spectrogram.channels'][i_channel]['color-map'] = \
            es.cfg[f'visualization.style.spectrogram.channels.ch{i_channel}.color-map'] if \
                es.cfg[f'visualization.style.spectrogram.channels.ch{i_channel}.color-map'] is not None else \
                es.cfg['visualization.style.spectrogram.channels.ch0.color-map']


def _parse_resolution(resolution) -> typing.Tuple[int, int]:
    try:
        width, height = resolution.split('x')
        width = int(width.strip())
        height = int(height.strip())
        return width, height
    except ValueError:
        raise ValueError(
            'Invalid resolution format. Provide the resolution as a string in the format "widthxheight", e.g. "1920x1080".')


es.add_event_listener('config.updated', _on_config_updated)
