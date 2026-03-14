"""Qt-based player window for EstimPy audio visualization.

Replaces the matplotlib-based VideoPlayerVisualization with a native Qt window
that uses the direct render pipeline (shift-and-paint) for high-performance
frame updates, and platform-native Qt widgets for controls.
"""
import math
import sys

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QImage, QPainter, QKeyEvent, QWheelEvent, QMouseEvent, QPixmap, QColor, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QStyle, QApplication, QSizePolicy,
    QCheckBox
)

import estimpy as es

# Predefined zoom levels (window lengths in seconds)
ZOOM_LEVELS = [1, 2, 5, 10, 20, 30, 40, 60, 120, 300, 600, 1200, 1800, 2400, 3600]

# Predefined oscilloscope duration steps (in milliseconds)
OSC_DURATIONS = [1, 2, 3, 5, 10, 15, 20, 25, 50, 75, 100, 150, 200, 250, 500, 1000]

# Module-level reference to QApplication to prevent garbage collection.
# In PyQt6, QApplication is destroyed when its Python reference is lost,
# which would crash any subsequent QWidget creation.
_qt_app = None


class VisualizationWidget(QWidget):
    """Custom widget that displays rendered video frames via QImage.

    Single-click toggles play/pause (with a short delay to distinguish from
    double-click). Double-click toggles fullscreen.
    """

    def __init__(self, player_window):
        super().__init__()
        self._player_window = player_window
        self._qimage = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 180)

        # Delayed single-click timer (VLC-style: wait for possible double-click
        # before committing to a play/pause toggle)
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(QApplication.doubleClickInterval())
        self._click_timer.timeout.connect(self._on_single_click)

    def set_image(self, qimage: QImage):
        self._qimage = qimage
        self.update()

    def paintEvent(self, event):
        if self._qimage is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Use logical dimensions (physical pixels / DPR) since QPainter works in logical coords
        dpr = self._qimage.devicePixelRatio()
        img_w = self._qimage.width() / dpr
        img_h = self._qimage.height() / dpr
        widget_w, widget_h = self.width(), self.height()

        # Scale maintaining aspect ratio, centered
        scale = min(widget_w / img_w, widget_h / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)
        x = (widget_w - scaled_w) // 2
        y = (widget_h - scaled_h) // 2

        painter.drawImage(QRect(x, y, scaled_w, scaled_h), self._qimage)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_click_pos = event.position()
            self._click_timer.start()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._player_window._player.toggle_full_screen()

    def _on_single_click(self):
        # Check if the click was on a scrub panel — if so, seek to that time
        pos = getattr(self, '_last_click_pos', None)
        if pos is not None:
            t = self._hit_test_scrub(pos.x(), pos.y())
            if t is not None:
                self._player_window._player.set_time(t)
                return
        self._player_window._player.toggle_playing()

    def _hit_test_scrub(self, widget_x, widget_y):
        """Map a widget click position to a time if it falls within a scrub panel.
        Returns the time in seconds, or None if not in a scrub region."""
        viz = self._player_window._visualization
        if viz is None or not hasattr(viz, '_scrub_regions') or self._qimage is None:
            return None

        # Map widget coordinates to frame buffer pixel coordinates
        dpr = self._qimage.devicePixelRatio()
        img_w = self._qimage.width() / dpr
        img_h = self._qimage.height() / dpr
        widget_w, widget_h = self.width(), self.height()
        scale = min(widget_w / img_w, widget_h / img_h)
        scaled_w = img_w * scale
        scaled_h = img_h * scale
        offset_x = (widget_w - scaled_w) / 2
        offset_y = (widget_h - scaled_h) / 2

        # Convert widget coords to image coords
        buf_x = (widget_x - offset_x) / scale * dpr
        buf_y = (widget_y - offset_y) / scale * dpr

        # Check each scrub region
        audio_length = self._player_window._es_audio.length
        for key, (x0, y0, x1, y1) in viz._scrub_regions.items():
            if x0 <= buf_x <= x1 and y0 <= buf_y <= y1:
                frac = (buf_x - x0) / (x1 - x0)
                return max(0, min(audio_length, frac * audio_length))

        return None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self._player_window._player.step_volume(volume_step=es.cfg['player.volume-step'])
        elif delta < 0:
            self._player_window._player.step_volume(volume_step=-es.cfg['player.volume-step'])
        self._player_window._sync_volume_sliders()


class PlayerWindow(QMainWindow):
    """Main Qt window for the EstimPy player.

    Uses the direct render pipeline (prepare_direct_render + render_frame_direct)
    with a QTimer for frame updates. Controls use native Qt widgets with
    platform-appropriate icons.
    """

    def __init__(self, player, es_audio):
        global _qt_app
        # QApplication must exist before QMainWindow can be created
        if QApplication.instance() is None:
            _qt_app = QApplication(sys.argv)

        super().__init__()
        self._player = player
        self._es_audio = es_audio
        self._ss_original_file = None
        self._ramp_active = False
        self._ramp_start_time = 0.0
        self._fps = es.cfg['visualization.video.export.fps']
        self._total_frames = max(1, math.floor(es_audio.length * self._fps))
        self._seeking = False
        self._full_screen = False
        self._playlist_window = None

        # Initialize oscilloscope duration controls (before _init_visualization which reads them)
        self._osc_auto = True
        default_tone = es.cfg['analysis.oscilloscope.window-length']
        self._osc_duration_index = 0
        for i, d in enumerate(OSC_DURATIONS):
            if d <= default_tone:
                self._osc_duration_index = i

        # Initialize visualization and direct render pipeline
        self._visualization = None
        self._init_visualization(self._get_viz_audio())

        # Initialize zoom
        self._init_zoom_levels(es_audio.length)

        # Set up the window
        self.setWindowTitle(es_audio.get_string())
        self._setup_ui()
        self._setup_timer()
        self._setup_dark_theme()

        # Render initial frame
        self._render_frame_at_time(0)

        # Set initial window size
        width = es.cfg['visualization.video.display.width']
        height = es.cfg['visualization.video.display.height']
        self.resize(width, height + self._controls.sizeHint().height())

    def _init_visualization(self, es_audio):
        """Create visualization and run chrome capture for direct rendering."""
        import matplotlib.pyplot

        # Get device pixel ratio early (needed for nfft optimization and figure sizing)
        self._device_pixel_ratio = self.devicePixelRatioF()

        # Apply player-specific spectrogram optimizations before creating the
        # visualization (which triggers spectrogram computation)
        if not es.cfg['player.spectrogram-reassign']:
            es.cfg['analysis.spectrogram.reassign'] = False

        es.visualization.set_optimal_nfft(
            es_audio, figure_height=es.cfg['visualization.video.display.height'] * self._device_pixel_ratio,
            triphase=es.cfg['visualization.video.display.triphase'],
            title_enabled=es.cfg['visualization.video.display.title.enabled'],
            include_scrub=True)

        with es.utils.Spinner('Preparing player visualization... '):
            self._visualization = es.visualization.VideoVisualization(
                es_audio=es_audio, mode=es.visualization.VisualizationMode.DISPLAY)
            self._visualization._window_length = es.cfg['visualization.video.display.window-length']
            self._visualization._fps = self._fps
            self._visualization._frames = range(self._total_frames)

            # Create matplotlib figure for chrome capture (skip initial frame rendering
            # since prepare_direct_render will paint frames on-demand, avoiding the
            # expensive full-spectrogram colormap allocation that make_frame(0) triggers)
            self._visualization.make_figure(skip_initial_frame=True)

            # Render at physical pixel resolution to avoid blurry text on HiDPI/Retina displays
            width = int(es.cfg['visualization.video.display.width'] * self._device_pixel_ratio)
            height = int(es.cfg['visualization.video.display.height'] * self._device_pixel_ratio)
            self._visualization.resize_figure(width=width, height=height)

            # One-time setup: capture chrome, axis overlays, initialize shift-and-paint state
            self._visualization.prepare_direct_render()
            self._visualization._osc_enabled = es.cfg['visualization.video.display.oscilloscope.enabled']
            self._visualization._osc_manual_duration = (
                None if self._osc_auto
                else OSC_DURATIONS[self._osc_duration_index] / 1000.0)

            # Hide the matplotlib figure window (frames are displayed in the Qt widget)
            fig = self._visualization._handles['figure']
            if fig and fig.canvas and fig.canvas.manager:
                fig.canvas.manager.window.hide()

    def _get_viz_audio(self):
        """Get the audio for visualization (always 3-channel for stereo to enable instant triphase toggle)."""
        if self._es_audio.channels == 2:
            return self._es_audio.with_triphase()
        return self._es_audio

    def _setup_ui(self):
        """Set up the window layout with visualization widget and controls."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Visualization widget
        self._viz_widget = VisualizationWidget(self)
        layout.addWidget(self._viz_widget, stretch=1)

        # Controls container
        self._controls = QWidget()
        controls_layout = QVBoxLayout(self._controls)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        controls_layout.setSpacing(4)

        # --- Seek bar row ---
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)

        self._time_label = QLabel(self._format_time(0))
        self._time_label.setFixedWidth(140)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seek_row.addWidget(self._time_label)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, max(1, self._total_frames - 1))
        self._seek_slider.setValue(0)
        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        self._seek_slider.valueChanged.connect(self._on_seek_changed)
        seek_row.addWidget(self._seek_slider, stretch=1)

        controls_layout.addLayout(seek_row)

        # --- Button/controls row ---
        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        style = self.style()
        btn_size = 32
        btn_size_play = 40

        # Playback buttons
        self._btn_prev = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaSkipBackward, btn_size,
            'Previous file (PageUp)', lambda: self._player.previous_file())
        button_row.addWidget(self._btn_prev)

        self._btn_skip_back = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaSeekBackward, btn_size,
            f'Skip back {es.cfg["player.skip-length"]}s (Left)',
            lambda: self._player.set_time(self._player.get_time() - es.cfg['player.skip-length']))
        button_row.addWidget(self._btn_skip_back)

        self._btn_play_pause = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaPlay, btn_size_play,
            'Play/Pause (Space)', lambda: self._player.toggle_playing())
        button_row.addWidget(self._btn_play_pause)

        self._btn_stop = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaStop, btn_size,
            'Stop', lambda: self._player.stop())
        button_row.addWidget(self._btn_stop)

        self._btn_skip_fwd = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaSeekForward, btn_size,
            f'Skip forward {es.cfg["player.skip-length"]}s (Right)',
            lambda: self._player.set_time(self._player.get_time() + es.cfg['player.skip-length']))
        button_row.addWidget(self._btn_skip_fwd)

        self._btn_next = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaSkipForward, btn_size,
            'Next file (PageDown)', lambda: self._player.next_file())
        button_row.addWidget(self._btn_next)

        self._add_separator(button_row)

        # --- Repeat button ---
        self._btn_repeat = self._make_text_button(
            '\u21BB', 28, 'Repeat: Off (R)',
            lambda: self._cycle_repeat(), width=36)
        self._btn_repeat.setCheckable(True)
        self._update_repeat_button()
        button_row.addWidget(self._btn_repeat)

        self._add_separator(button_row)

        # --- Fullscreen button ---
        self._btn_fullscreen = self._make_text_button(
            '\u26F6', 28, 'Fullscreen (F)',
            lambda: self._player.toggle_full_screen())
        self._btn_fullscreen.setCheckable(True)
        button_row.addWidget(self._btn_fullscreen)

        self._add_separator(button_row)

        # --- Playlist button ---
        self._btn_playlist = self._make_text_button(
            '\u2630', 28, 'Playlist (P)',
            lambda: self._toggle_playlist())
        button_row.addWidget(self._btn_playlist)

        button_row.addStretch(1)

        # --- Oscilloscope duration controls ---
        self._add_osc_controls(button_row)

        self._add_separator(button_row)

        # --- Zoom controls ---
        self._add_zoom_controls(button_row)

        self._add_separator(button_row)

        # --- Volume controls ---
        self._volume_widgets = {}

        # Master volume (buttons only)
        self._add_master_volume(button_row)

        # Per-channel volume container (rebuilt when channel count changes)
        self._channel_vol_container = QWidget()
        self._channel_vol_layout = QHBoxLayout(self._channel_vol_container)
        self._channel_vol_layout.setContentsMargins(0, 0, 0, 0)
        self._channel_vol_layout.setSpacing(4)
        self._rebuild_channel_volumes()
        button_row.addWidget(self._channel_vol_container)

        self._add_separator(button_row)

        # --- Ramp controls ---
        self._btn_ramp = self._make_text_button(
            'Start Ramp', 28, 'Start amplitude ramp (G)',
            lambda: self._start_ramp(), width=90)
        button_row.addWidget(self._btn_ramp)

        self._ramp_gain_label = QLabel('')
        self._ramp_gain_label.setFixedWidth(32)
        self._ramp_gain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_row.addWidget(self._ramp_gain_label)

        ramp_level_label = QLabel('Level')
        ramp_level_label.setFixedWidth(30)
        button_row.addWidget(ramp_level_label)

        self._ramp_level_slider = QSlider(Qt.Orientation.Horizontal)
        self._ramp_level_slider.setRange(0, 100)
        self._ramp_level_slider.setValue(es.cfg['audio.ramp.level'])
        self._ramp_level_slider.setFixedWidth(60)
        self._ramp_level_slider.valueChanged.connect(self._on_ramp_level_changed)
        button_row.addWidget(self._ramp_level_slider)

        self._ramp_level_value = QLabel(str(es.cfg['audio.ramp.level']))
        self._ramp_level_value.setFixedWidth(22)
        self._ramp_level_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_row.addWidget(self._ramp_level_value)

        shape_label = QLabel('Shape')
        shape_label.setFixedWidth(34)
        button_row.addWidget(shape_label)

        self._ramp_shape_slider = QSlider(Qt.Orientation.Horizontal)
        self._ramp_shape_slider.setRange(-10, 10)
        self._ramp_shape_slider.setValue(int(es.cfg['audio.ramp.shape']))
        self._ramp_shape_slider.setFixedWidth(60)
        self._ramp_shape_slider.valueChanged.connect(self._on_ramp_shape_changed)
        button_row.addWidget(self._ramp_shape_slider)

        self._ramp_shape_value = QLabel(str(int(es.cfg['audio.ramp.shape'])))
        self._ramp_shape_value.setFixedWidth(18)
        self._ramp_shape_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_row.addWidget(self._ramp_shape_value)

        self._add_separator(button_row)

        # --- Triphase toggle button (wrapped in channel-colored container) ---
        self._triphase_container = QWidget()
        triphase_layout = QHBoxLayout(self._triphase_container)
        triphase_layout.setContentsMargins(4, 2, 4, 2)
        triphase_layout.setSpacing(0)
        self._btn_triphase = self._make_text_button(
            'Triphase', 28, 'Triphase (T)',
            lambda: self._toggle_triphase(), width=70)
        self._btn_triphase.setCheckable(True)
        self._btn_triphase.setChecked(es.cfg['visualization.video.display.triphase'])
        self._btn_triphase.setEnabled(self._es_audio.channels == 2)
        triphase_layout.addWidget(self._btn_triphase)
        self._apply_channel_tint(self._triphase_container, channel_id=2)
        button_row.addWidget(self._triphase_container)

        # --- Stereo stim toggle button ---
        self._btn_ss = self._make_text_button(
            'SS', 28, 'Stereo Stim (S)',
            lambda: self._toggle_ss(), width=34)
        self._btn_ss.setCheckable(True)
        self._btn_ss.setChecked(es.cfg['audio.stereo-stim.enabled'])
        button_row.addWidget(self._btn_ss)

        controls_layout.addLayout(button_row)
        layout.addWidget(self._controls)

    def _make_icon_button(self, icon_pixmap, size, tooltip, callback):
        """Create a QPushButton with a standard icon recolored for the dark theme."""
        btn = QPushButton()
        btn.setIcon(self._recolor_icon(icon_pixmap))
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def _recolor_icon(self, icon_pixmap, color=QColor(0xcc, 0xcc, 0xcc)):
        """Recolor a standard icon to match the dark theme text color."""
        icon = self.style().standardIcon(icon_pixmap)
        pixmap = icon.pixmap(64, 64)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        return QIcon(pixmap)

    def _make_text_button(self, text, size, tooltip, callback, width=None):
        """Create a QPushButton with text label."""
        btn = QPushButton(text)
        btn.setFixedSize(width if width is not None else size, size)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def _add_separator(self, layout):
        """Add a vertical separator to a layout."""
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setFixedHeight(28)
        sep.setObjectName('separator')
        sep.setStyleSheet('#separator { background-color: #555; }')
        layout.addWidget(sep)

    def _add_master_volume(self, layout):
        """Add master volume controls (label + mute + vol down + vol up)."""
        label = QLabel('All')
        label.setFixedWidth(24)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        mute_btn = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaVolume, 28,
            'Mute/Unmute all', lambda: self._player.toggle_muted(None))
        layout.addWidget(mute_btn)

        vol_down_btn = self._make_text_button(
            '-', 24, 'Volume down (all)',
            lambda: self._on_volume_step(-es.cfg['player.volume-step'], None))
        layout.addWidget(vol_down_btn)

        vol_up_btn = self._make_text_button(
            '+', 24, 'Volume up (all)',
            lambda: self._on_volume_step(es.cfg['player.volume-step'], None))
        layout.addWidget(vol_up_btn)

        self._volume_widgets['master'] = {
            'mute_btn': mute_btn,
        }

    def _apply_channel_tint(self, widget, channel_id):
        """Apply a subtle channel-colored background tint to a container widget."""
        from estimpy.visualization import _alpha_color
        channel_cfg = es.cfg['visualization.style.channels']
        if channel_id < len(channel_cfg):
            color = channel_cfg[channel_id]['color']
        else:
            color = channel_cfg[0]['color']
        bg = _alpha_color(color, '#1a1a1a', 0.25)
        widget.setStyleSheet(f'background-color: {bg}; border-radius: 4px;')

    def _add_channel_volume(self, container_layout, channel_id, label_text):
        """Add per-channel volume controls (label + mute + slider + value label) in a tinted container."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        label = QLabel(label_text)
        label.setFixedWidth(20)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        mute_btn = self._make_icon_button(
            QStyle.StandardPixmap.SP_MediaVolume, 28,
            f'Mute/Unmute channel {label_text}',
            lambda checked, ch=channel_id: self._player.toggle_muted(ch))
        layout.addWidget(mute_btn)

        initial_vol = self._player.get_channel_volume(channel_id)
        if initial_vol is None:
            initial_vol = es.cfg['player.volume-start']

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(initial_vol))
        slider.setFixedWidth(80)
        slider.setToolTip(f'Volume channel {label_text}')
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.valueChanged.connect(
            lambda val, ch=channel_id: self._on_volume_slider_changed(val, ch))
        layout.addWidget(slider)

        vol_label = QLabel(str(int(initial_vol)))
        vol_label.setFixedWidth(58)
        vol_label.setContentsMargins(4, 0, 0, 0)
        vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(vol_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._apply_channel_tint(container, channel_id)
        container_layout.addWidget(container)

        self._volume_widgets[channel_id] = {
            'mute_btn': mute_btn,
            'slider': slider,
            'vol_label': vol_label,
        }

    def _rebuild_channel_volumes(self):
        """Rebuild per-channel volume controls for the current audio's channel count."""
        # Clear existing widgets
        while self._channel_vol_layout.count():
            item = self._channel_vol_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Remove old per-channel entries from _volume_widgets
        for key in list(self._volume_widgets.keys()):
            if key != 'master':
                del self._volume_widgets[key]

        # Add controls for each channel using configured labels
        channel_cfgs = es.cfg['visualization.style.channels']
        for ch in range(self._es_audio.channels):
            label = channel_cfgs[ch]['label'] if ch < len(channel_cfgs) else chr(ch + 65)
            self._add_channel_volume(self._channel_vol_layout, channel_id=ch, label_text=label)

    def _init_zoom_levels(self, audio_duration, target_length=None):
        """Build the list of available zoom levels for the current audio file.

        :param audio_duration: Duration of the audio file in seconds.
        :param target_length: Desired window length to match. If None, uses the
            configured default. Used to preserve the user's zoom level across
            file changes.
        """
        # Filter predefined levels to those shorter than the audio duration
        self._zoom_levels = [level for level in ZOOM_LEVELS if level < audio_duration]
        # Add full duration as the final (fully zoomed out) level
        self._zoom_levels.append(audio_duration)

        # Find the zoom index closest to the target window length
        if target_length is None:
            target_length = es.cfg['visualization.video.display.window-length']
        self._zoom_index = 0
        for i, level in enumerate(self._zoom_levels):
            if level <= target_length:
                self._zoom_index = i
            else:
                break

    def _add_zoom_controls(self, layout):
        """Add zoom in/out controls (label + buttons + value)."""
        btn_size = 24

        zoom_text = QLabel('Zoom')
        zoom_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(zoom_text)

        self._btn_zoom_in = self._make_text_button(
            '\u2212', btn_size, 'Zoom in - shorter window ([)',
            lambda: self._on_zoom_in())
        layout.addWidget(self._btn_zoom_in)

        is_full = (self._zoom_index == len(self._zoom_levels) - 1)
        initial_label = 'Full' if is_full else self._format_zoom_label(self._zoom_levels[self._zoom_index])
        self._zoom_label = QLabel(initial_label)
        self._zoom_label.setFixedWidth(40)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setToolTip('Sliding window length')
        layout.addWidget(self._zoom_label)

        self._btn_zoom_out = self._make_text_button(
            '+', btn_size, 'Zoom out - longer window (])',
            lambda: self._on_zoom_out())
        layout.addWidget(self._btn_zoom_out)

        self._update_zoom_buttons()

    def _on_zoom_in(self):
        """Zoom in: decrease window length (more detail)."""
        if self._zoom_index > 0:
            self._zoom_index -= 1
            self._apply_zoom()

    def _on_zoom_out(self):
        """Zoom out: increase window length (less detail)."""
        if self._zoom_index < len(self._zoom_levels) - 1:
            self._zoom_index += 1
            self._apply_zoom()

    def _apply_zoom(self):
        """Apply the current zoom level to the visualization."""
        new_length = self._zoom_levels[self._zoom_index]
        is_full = (self._zoom_index == len(self._zoom_levels) - 1)
        self._visualization.update_window_length(new_length)
        self._zoom_label.setText('Full' if is_full else self._format_zoom_label(new_length))
        self._update_zoom_buttons()

        # Re-render the current frame with the new window length
        current_time = self._player.get_time()
        self._render_frame_at_time(current_time)

    def _update_zoom_buttons(self):
        """Enable/disable zoom buttons based on current zoom level."""
        self._btn_zoom_in.setEnabled(self._zoom_index > 0)
        self._btn_zoom_out.setEnabled(self._zoom_index < len(self._zoom_levels) - 1)

    @staticmethod
    def _format_zoom_label(seconds):
        """Format a window length as a human-readable label."""
        if seconds >= 3600 and seconds % 3600 == 0:
            return f'{int(seconds // 3600)}h'
        elif seconds >= 60:
            minutes = seconds / 60
            if minutes == int(minutes):
                return f'{int(minutes)}m'
            return f'{minutes:.1f}m'
        else:
            if seconds == int(seconds):
                return f'{int(seconds)}s'
            return f'{seconds:.1f}s'

    def _add_osc_controls(self, layout):
        """Add oscilloscope duration controls (auto checkbox + buttons + value)."""
        btn_size = 24

        self._chk_osc_auto = QCheckBox('Osc auto')
        self._chk_osc_auto.setChecked(self._osc_auto)
        self._chk_osc_auto.setToolTip('Automatic oscilloscope duration')
        self._chk_osc_auto.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._chk_osc_auto.stateChanged.connect(self._on_osc_auto_changed)
        layout.addWidget(self._chk_osc_auto)

        self._btn_osc_minus = self._make_text_button(
            '\u2212', btn_size, 'Decrease oscilloscope duration',
            lambda: self._on_osc_decrease())
        layout.addWidget(self._btn_osc_minus)

        dur_ms = OSC_DURATIONS[self._osc_duration_index]
        self._osc_label = QLabel(self._format_osc_label(dur_ms))
        self._osc_label.setFixedWidth(48)
        self._osc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._osc_label.setToolTip('Oscilloscope display duration')
        layout.addWidget(self._osc_label)

        self._btn_osc_plus = self._make_text_button(
            '+', btn_size, 'Increase oscilloscope duration',
            lambda: self._on_osc_increase())
        layout.addWidget(self._btn_osc_plus)

        self._update_osc_controls()

    def _on_osc_auto_changed(self, state):
        """Handle oscilloscope auto checkbox toggle."""
        self._osc_auto = (state == Qt.CheckState.Checked.value)
        self._update_osc_controls()
        self._apply_osc_duration()

    def _on_osc_decrease(self):
        """Decrease oscilloscope duration to previous step."""
        if self._osc_duration_index > 0:
            self._osc_duration_index -= 1
            self._update_osc_controls()
            self._apply_osc_duration()

    def _on_osc_increase(self):
        """Increase oscilloscope duration to next step."""
        if self._osc_duration_index < len(OSC_DURATIONS) - 1:
            self._osc_duration_index += 1
            self._update_osc_controls()
            self._apply_osc_duration()

    def _apply_osc_duration(self):
        """Apply the current oscilloscope duration setting to the visualization."""
        if self._osc_auto:
            self._visualization._osc_manual_duration = None
            self._osc_label.setText('Auto')
        else:
            dur_ms = OSC_DURATIONS[self._osc_duration_index]
            self._visualization._osc_manual_duration = dur_ms / 1000.0
            self._osc_label.setText(self._format_osc_label(dur_ms))

        # Invalidate correlation template since duration changed
        self._visualization._dr_osc_prev_waveform.clear()

        # Re-render current frame
        current_time = self._player.get_time()
        self._render_frame_at_time(current_time)

    def _update_osc_controls(self):
        """Enable/disable oscilloscope +/- buttons based on auto mode and index."""
        manual = not self._osc_auto
        self._btn_osc_minus.setEnabled(manual and self._osc_duration_index > 0)
        self._btn_osc_plus.setEnabled(manual and self._osc_duration_index < len(OSC_DURATIONS) - 1)
        if self._osc_auto:
            self._osc_label.setText('Auto')
        else:
            self._osc_label.setText(self._format_osc_label(OSC_DURATIONS[self._osc_duration_index]))

    @staticmethod
    def _format_osc_label(ms):
        """Format an oscilloscope duration in ms as a label."""
        if ms >= 1000:
            return f'{ms / 1000:.0f} s'
        return f'{int(ms)} ms'

    def _cycle_repeat(self):
        """Cycle through repeat modes: none → all → one → none."""
        mode = self._player.get_repeat_mode()
        if mode == 'none':
            new_mode = 'all'
        elif mode == 'all':
            new_mode = 'one'
        else:
            new_mode = 'none'
        es.cfg['player.repeat'] = new_mode
        self._update_repeat_button()

    def _update_repeat_button(self):
        """Update repeat button text and checked state to reflect current mode."""
        mode = self._player.get_repeat_mode()
        if mode == 'none':
            self._btn_repeat.setText('\u21BB')
            self._btn_repeat.setChecked(False)
            self._btn_repeat.setToolTip('Repeat: Off (R)')
        elif mode == 'all':
            self._btn_repeat.setText('\u21BB')
            self._btn_repeat.setChecked(True)
            self._btn_repeat.setToolTip('Repeat: All (R)')
        else:  # 'one'
            self._btn_repeat.setText('\u21BB1')
            self._btn_repeat.setChecked(True)
            self._btn_repeat.setToolTip('Repeat: One (R)')

    def _toggle_playlist(self):
        """Show or hide the playlist window."""
        from estimpy.player.playlist_window import PlaylistWindow

        if self._playlist_window is None:
            self._playlist_window = PlaylistWindow(self)

        if self._playlist_window.isVisible():
            self._playlist_window.hide()
        else:
            self._playlist_window.show()
            self._playlist_window.raise_()
            self._playlist_window.activateWindow()

    def _rebuild_visualization_figure(self):
        """Rebuild visualization figure without recomputing analysis data.

        Closes the old matplotlib figure, creates a new one with the current
        channel layout, and re-initializes the direct render pipeline. Reuses
        cached envelopes and spectrogram data for instant layout changes.
        """
        import matplotlib.pyplot

        if self._visualization and self._visualization._handles.get('figure'):
            matplotlib.pyplot.close(self._visualization._handles['figure'])

        self._visualization.make_figure(skip_initial_frame=True)

        width = int(es.cfg['visualization.video.display.width'] * self._device_pixel_ratio)
        height = int(es.cfg['visualization.video.display.height'] * self._device_pixel_ratio)
        self._visualization.resize_figure(width=width, height=height)

        self._visualization.prepare_direct_render()
        self._visualization._osc_enabled = es.cfg['visualization.video.display.oscilloscope.enabled']
        self._visualization._osc_manual_duration = (
            None if self._osc_auto
            else OSC_DURATIONS[self._osc_duration_index] / 1000.0)

        fig = self._visualization._handles['figure']
        if fig and fig.canvas and fig.canvas.manager:
            fig.canvas.manager.window.hide()

    def _toggle_triphase(self):
        """Toggle triphase visualization mode."""
        new_state = not es.cfg['visualization.video.display.triphase']
        es.cfg['visualization.video.display.triphase'] = new_state
        self._btn_triphase.setChecked(new_state)

        # Rebuild figure layout (reuses cached analysis data for instant toggle)
        self._rebuild_visualization_figure()

        # Re-render current frame
        current_time = self._player.get_time()
        self._render_frame_at_time(current_time)

    def _toggle_ss(self):
        """Toggle stereo stim mode. Reprocesses audio and rebuilds visualization."""
        new_state = not es.cfg['audio.stereo-stim.enabled']
        es.cfg['audio.stereo-stim.enabled'] = new_state
        self._btn_ss.setChecked(new_state)

        was_playing = self._player.is_playing()
        current_time = self._player.get_time()
        if was_playing:
            self._player.stop()

        # Reload audio with or without stereo stim filtering
        if new_state:
            self._ss_original_file = self._es_audio.file
            with es.utils.Spinner('Applying stereo stim... '):
                ss_audio = self._es_audio.with_stereo_stim()
        else:
            ss_audio = es.audio.Audio(file=self._ss_original_file)
            self._ss_original_file = None

        # Reload into player and rebuild visualization
        self._player.set_audio(es_audio=ss_audio)

        if was_playing:
            self._player.set_time(current_time)
            self._player.toggle_playing()

    def _start_ramp(self):
        """Start (or restart) the amplitude ramp from the current playback position."""
        self._ramp_active = True
        self._ramp_start_time = es.player.audio.get_time() if self._player.is_playing() else 0.0
        self._btn_ramp.setText('Restart Ramp')
        # Apply initial gain immediately
        gain = es.audio.compute_ramp_gain(
            self._ramp_start_time, self._ramp_start_time, self._es_audio.length,
            es.cfg['audio.ramp.level'], es.cfg['audio.ramp.shape'])
        es.player.audio.set_ramp_gain(gain)
        self._ramp_gain_label.setText(f'{int(gain * 100)}%')

    def _stop_ramp(self):
        """Reset ramp state and restore full volume."""
        self._ramp_active = False
        self._ramp_start_time = 0.0
        self._btn_ramp.setText('Start Ramp')
        es.player.audio.set_ramp_gain(1.0)
        self._ramp_gain_label.setText('')

    def _on_ramp_level_changed(self, value):
        """Handle ramp level slider change."""
        es.cfg['audio.ramp.level'] = value
        self._ramp_level_value.setText(str(value))

    def _on_ramp_shape_changed(self, value):
        """Handle ramp shape slider change."""
        es.cfg['audio.ramp.shape'] = value
        self._ramp_shape_value.setText(str(value))

    def update_playlist(self):
        """Update the playlist window to reflect current player state."""
        if self._playlist_window is not None:
            self._playlist_window.set_files(self._player.get_audio_files())
            self._playlist_window.set_current_file(self._player.get_current_file_index())

    def _setup_timer(self):
        """Set up the frame update timer."""
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, 1000 // self._fps))
        self._timer.timeout.connect(self._on_timer)

    def _setup_dark_theme(self):
        """Apply dark theme to the controls to match the visualization."""
        self._controls.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: #cccccc;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #4a4a4a;
                border-color: #888;
            }
            QSlider::groove:horizontal {
                border: 1px solid #444;
                height: 6px;
                background: #2a2a2a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #888;
                border: 1px solid #666;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #aaa;
            }
            QLabel {
                font-size: 13px;
                background-color: transparent;
            }
        """)
        self._viz_widget.setStyleSheet('background-color: black;')

    # --- Timer and rendering ---

    def _on_timer(self):
        """Timer callback: render and display the current frame during playback."""
        if not self._player.is_playing():
            return

        audio_time = es.player.audio.get_time()
        if not es.player.audio.is_playing():
            # Audio finished playback — handle repeat/playlist advancement
            self._player.on_track_finished()
            return

        display_time = audio_time + es.cfg['player.video-render-latency']
        display_time = min(display_time, self._es_audio.length)

        frame = int(display_time * self._fps)
        frame = max(0, min(frame, self._total_frames - 1))

        self._render_and_display(frame)

        # Update seek slider
        if not self._seeking:
            self._seek_slider.blockSignals(True)
            self._seek_slider.setValue(frame)
            self._seek_slider.blockSignals(False)

        # Update time label
        self._time_label.setText(self._format_time(audio_time))

        # Update ramp gain if active
        if self._ramp_active:
            gain = es.audio.compute_ramp_gain(
                audio_time, self._ramp_start_time, self._es_audio.length,
                es.cfg['audio.ramp.level'], es.cfg['audio.ramp.shape'])
            es.player.audio.set_ramp_gain(gain)
            self._ramp_gain_label.setText(f'{int(gain * 100)}%')

        # Sync volume sliders from player state
        self._sync_volume_sliders()

    def _render_and_display(self, frame):
        """Render a frame via the direct render pipeline and display it."""
        rgb_array = self._visualization.render_frame_direct(frame)
        h, w, ch = rgb_array.shape
        qimage = QImage(rgb_array.data, w, h, w * ch, QImage.Format.Format_RGB888)
        # Mark the image as HiDPI so Qt maps it 1:1 to physical pixels (no upscaling blur)
        qimage.setDevicePixelRatio(self._device_pixel_ratio)
        self._viz_widget.set_image(qimage)

    def _render_frame_at_time(self, t):
        """Render and display the frame at the given time, update UI elements."""
        t = max(0, min(t, self._es_audio.length))
        frame = max(0, min(int(t * self._fps), self._total_frames - 1))
        self._render_and_display(frame)
        self._time_label.setText(self._format_time(t))

        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(frame)
        self._seek_slider.blockSignals(False)

    def _format_time(self, t):
        """Format time as 'current / total' string."""
        return (es.utils.seconds_to_string(max(0, t)) + ' / '
                + es.utils.seconds_to_string(self._es_audio.length))

    def _sync_volume_sliders(self):
        """Sync per-channel volume sliders and labels from current state.

        Sliders show the target volume (what the user set).
        Labels show "target (current)" while a volume ramp is in progress,
        and just "target" once the ramp has settled.
        """
        for ch in range(self._es_audio.channels):
            target_vol = self._player.get_channel_volume(ch)
            if target_vol is not None and ch in self._volume_widgets:
                widgets = self._volume_widgets[ch]
                if 'slider' in widgets:
                    widgets['slider'].blockSignals(True)
                    widgets['slider'].setValue(int(target_vol))
                    widgets['slider'].blockSignals(False)
                if 'vol_label' in widgets:
                    current_vol = es.player.audio.get_current_volume(ch)
                    target_int = int(target_vol)
                    current_int = int(current_vol)
                    if current_int != target_int:
                        widgets['vol_label'].setText(f'{target_int} ({current_int})')
                    else:
                        widgets['vol_label'].setText(str(target_int))

    # --- Event handlers ---

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        self._seeking = False
        frame = self._seek_slider.value()
        t = frame / self._fps
        self._player.set_time(t)

    def _on_seek_changed(self, value):
        if self._seeking:
            # Live preview while dragging
            t = value / self._fps
            self._render_frame_at_time(t)

    def _on_volume_slider_changed(self, value, channel):
        """Handle per-channel volume slider change."""
        self._player.set_volume(volume=value, channel=channel)
        self._sync_volume_sliders()

    def _on_volume_step(self, step, channel):
        """Handle volume up/down button press."""
        self._player.step_volume(volume_step=step, channel=channel)
        self._sync_volume_sliders()

    # --- Public interface (called by Player) ---

    def load(self, es_audio):
        """Load a new audio file and re-initialize the visualization."""
        was_playing = self._player.is_playing()
        self._timer.stop()

        self._es_audio = es_audio
        self._total_frames = max(1, math.floor(es_audio.length * self._fps))

        # Close old matplotlib figure
        import matplotlib.pyplot
        if self._visualization and self._visualization._handles.get('figure'):
            matplotlib.pyplot.close(self._visualization._handles['figure'])

        # Re-initialize visualization
        self._init_visualization(self._get_viz_audio())

        # Update toggle button states
        self._btn_triphase.setEnabled(es_audio.channels == 2)
        if es_audio.channels != 2:
            self._btn_triphase.setChecked(False)
        else:
            self._btn_triphase.setChecked(es.cfg['visualization.video.display.triphase'])
        self._btn_ss.setChecked(es.cfg['audio.stereo-stim.enabled'])

        # Reset ramp state for new file
        self._stop_ramp()

        # Rebuild per-channel volume controls if channel count changed
        self._rebuild_channel_volumes()

        # Re-initialize zoom levels for new audio, preserving the user's current window length
        current_window_length = self._zoom_levels[self._zoom_index]
        self._init_zoom_levels(es_audio.length, target_length=current_window_length)

        # Apply the preserved zoom level to the visualization
        new_length = self._zoom_levels[self._zoom_index]
        self._visualization.update_window_length(new_length)

        is_full = (self._zoom_index == len(self._zoom_levels) - 1)
        self._zoom_label.setText('Full' if is_full else self._format_zoom_label(
            self._zoom_levels[self._zoom_index]))
        self._update_zoom_buttons()

        # Update UI
        self.setWindowTitle(es_audio.get_string())
        self._seek_slider.setRange(0, max(1, self._total_frames - 1))
        self._seek_slider.setValue(0)
        self._time_label.setText(self._format_time(0))

        # Render initial frame
        self._render_frame_at_time(0)

        # Update playlist window
        if self._playlist_window is not None:
            self._playlist_window.set_current_file(self._player.get_current_file_index())

        if was_playing:
            self._timer.start()

    def mute(self, channel=None):
        """Update mute button icon to muted state."""
        key = 'master' if channel is None else channel
        if key in self._volume_widgets:
            self._volume_widgets[key]['mute_btn'].setIcon(
                self._recolor_icon(QStyle.StandardPixmap.SP_MediaVolumeMuted))

    def unmute(self, channel=None):
        """Update mute button icon to unmuted state."""
        key = 'master' if channel is None else channel
        if key in self._volume_widgets:
            self._volume_widgets[key]['mute_btn'].setIcon(
                self._recolor_icon(QStyle.StandardPixmap.SP_MediaVolume))

    def pause(self):
        """Stop the frame timer and show play icon."""
        self._timer.stop()
        self._btn_play_pause.setIcon(
            self._recolor_icon(QStyle.StandardPixmap.SP_MediaPlay))

    def play(self):
        """Start the frame timer and show pause icon."""
        self._timer.start()
        self._btn_play_pause.setIcon(
            self._recolor_icon(QStyle.StandardPixmap.SP_MediaPause))

    def stop(self):
        """Stop the frame timer and show play icon."""
        self._timer.stop()
        self._btn_play_pause.setIcon(
            self._recolor_icon(QStyle.StandardPixmap.SP_MediaPlay))

    def set_time(self, t):
        """Render frame at the given time and update seek/time UI."""
        self._render_frame_at_time(t)

    def set_volume(self, volume, channel=None):
        """Update volume slider display for a channel."""
        if channel is not None and channel in self._volume_widgets:
            widgets = self._volume_widgets[channel]
            if 'slider' in widgets:
                widgets['slider'].blockSignals(True)
                widgets['slider'].setValue(int(volume))
                widgets['slider'].blockSignals(False)
        self._sync_volume_sliders()

    def toggle_full_screen(self):
        """Toggle between fullscreen and normal window."""
        if self._full_screen:
            self.showNormal()
            self._controls.show()
            self._full_screen = False
        else:
            self._controls.hide()
            self.showFullScreen()
            self._full_screen = True
        self._btn_fullscreen.setChecked(self._full_screen)

    def show_window(self):
        """Show the window and start the Qt event loop."""
        if es.cfg['player.autoplay']:
            self._player.play()

        self.show()
        QApplication.instance().exec()

    # --- Keyboard shortcuts ---

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Space:
            self._player.toggle_playing()
        elif key == Qt.Key.Key_Up:
            self._player.step_volume(volume_step=es.cfg['player.volume-step'])
            self._sync_volume_sliders()
        elif key == Qt.Key.Key_Down:
            self._player.step_volume(volume_step=-es.cfg['player.volume-step'])
            self._sync_volume_sliders()
        elif key == Qt.Key.Key_Left:
            self._player.set_time(self._player.get_time() - es.cfg['player.skip-length'])
        elif key == Qt.Key.Key_Right:
            self._player.set_time(self._player.get_time() + es.cfg['player.skip-length'])
        elif key == Qt.Key.Key_PageUp:
            self._player.previous_file()
        elif key == Qt.Key.Key_PageDown:
            self._player.next_file()
        elif key == Qt.Key.Key_Home:
            self._player.set_time(0)
        elif key == Qt.Key.Key_End:
            self._player.stop()
            self.close()
        elif key == Qt.Key.Key_Escape:
            if self._full_screen:
                self._player.toggle_full_screen()
        elif key == Qt.Key.Key_F:
            self._player.toggle_full_screen()
        elif key == Qt.Key.Key_Return and modifiers & Qt.KeyboardModifier.AltModifier:
            self._player.toggle_full_screen()
        elif key == Qt.Key.Key_R:
            self._cycle_repeat()
        elif key == Qt.Key.Key_BracketLeft:
            self._on_zoom_in()
        elif key == Qt.Key.Key_BracketRight:
            self._on_zoom_out()
        elif key == Qt.Key.Key_P:
            self._toggle_playlist()
        elif key == Qt.Key.Key_T:
            if self._es_audio.channels == 2:
                self._toggle_triphase()
        elif key == Qt.Key.Key_S:
            self._toggle_ss()
        elif key == Qt.Key.Key_G:
            self._start_ramp()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Clean up on window close."""
        self._timer.stop()
        if self._player.is_playing():
            es.player.audio.stop()

        # Close playlist window
        if self._playlist_window is not None:
            self._playlist_window.close()
            self._playlist_window.deleteLater()
            self._playlist_window = None

        # Close matplotlib figure
        import matplotlib.pyplot
        if self._visualization and self._visualization._handles.get('figure'):
            matplotlib.pyplot.close(self._visualization._handles['figure'])

        event.accept()
