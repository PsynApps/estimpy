# Changelog

## [2.0.0] - 2026-02-11
### Added
- Unified `estimpy` CLI replacing `estimpy-visualizer` and `estimpy-player` with subcommands: `play` (default), `show-image`, `save-image`, `save-video`, `save-metadata`
- Positional file arguments (e.g., `estimpy play song.mp3` instead of `estimpy-player -i song.mp3`)
- Configurable time text position (`top`/`bottom`) for image and video visualizations (`*.time.position`)

- Reassigned spectrogram algorithm for sharper time-frequency localization, with configurable smoothing (`analysis.spectrogram.reassign`, `analysis.spectrogram.reassign-smoothing`)
- Triphase visualization mode (`-t`/`--triphase`) showing the derived common electrode signal -(A+B) alongside the A and B channels
- Triphase toggle in the player UI for instant switching between stereo and triphase visualization during playback, with pre-computed 3-channel analysis data for stereo files
- Per-channel colormap derivation from a single base colormap (`visualization.style.spectrogram.color-map`), with the low-energy region automatically recolored to match each channel's base color
- Configurable colormap recoloring radius (`visualization.style.spectrogram.match-channel-color-radius`) with perceptual brightness matching using Rec. 709 relative luminance
- Playlist management UI in the player with add, remove, reorder, and file selection
- Repeat mode button in the player (none/one/all), toggled with the R key
- Fullscreen mode in the player, toggled via button, F key, Alt+Enter, or double-clicking the visualization (Escape to exit)
- Zoom controls in the player for adjusting the sliding window length
- Qt-based player window replacing the matplotlib-only interactive player
- Direct frame rendering pipeline for video export, bypassing matplotlib's animation framework and piping raw frames to ffmpeg
- Profiling mode for video export (`-p`/`--profiling`) to diagnose per-frame timing
- Third channel style configuration (`visualization.style.amplitude.channels.ch2`)
- Triphase subplot height ratios (`visualization.style.subplot-height-ratios.amplitude.triphase`, `visualization.style.subplot-height-ratios.spectrogram.triphase`)
- Pillow added as a package dependency
- Configuration profiles for HEVC and ProRes VideoToolbox hardware encoding, and iPod Touch player
- Configurable reassignment bypass for the player (`player.spectrogram-reassign`, default False) to speed up loading by using the standard spectrogram
- Resolution-aware FFT sizing for all visualization modes (player, image, and video export), using coarse frequency pre-analysis (~20 FFTs) and output panel dimensions to determine the optimal FFT size
- Oscilloscope waveform overlay for video display and export, showing trigger-stabilized raw audio waveform per channel with automatic pulse detection that switches window length between tonal and pulsed content using coefficient of variation analysis (`visualization.video.display.oscilloscope.enabled`, `visualization.video.export.oscilloscope.enabled`, `analysis.oscilloscope.pulse-detection.*`)
- Manual oscilloscope duration controls in the player UI (auto/manual mode with configurable duration stepping)
- Configurable channel identity labels (A, B, T) displayed on visualizations, centered across each channel's amplitude and spectrogram panels (`visualization.style.channels.labels.enabled`, `visualization.style.channels.labels.font-size`, `visualization.style.channels.chN.label`)
- Channel-colored background tints on per-channel volume controls and triphase button in the player, visually linking controls to their channel identity
- `benchmark` CLI subcommand for comparing video encoding profiles, reporting encoding time, speed, and file size across all `video-*` config profiles (`-o` to keep output files, `-c` to benchmark a specific profile combination)
- MOV container metadata support (read/write via mutagen's MP4/QuickTime handler)
- Automated test suite (251 tests) covering audio loading, DSP analysis, configuration, metadata, and utilities

### Changed
- Audio data stored as float32 instead of float64, halving memory usage for all audio operations
- Spectrogram computation uses float32/complex64 throughout, halving memory for all intermediate and final arrays
- Reassigned spectrogram computed in chunks to limit peak memory usage, with histograms accumulated across batches
- Raw audio data (`data_raw`) reconstructed on demand instead of stored as a duplicate copy
- Default FFT length automatically sized based on output resolution and frequency content, replacing the previous fixed 1x window size default
- Default window overlap increased to 75% (3/4 window size) for better temporal resolution
- Envelope computation vectorized using NumPy stride tricks, replacing per-window Python loop
- Spectral edge frequency max computation vectorized and subsampled for faster loading of long files
- Spectrogram colormap configuration simplified from per-channel colormaps to a single base colormap with automatic per-channel derivation
- Channel identity (color and label) promoted to `visualization.style.channels.chN` with per-channel amplitude styling (`peak-color`, `rms-color`, `background-color`) falling back to the channel color when not explicitly set
- Renamed `base-color` to `peak-color` in amplitude channel style configuration
- Renamed `match-amplitude-color` to `match-channel-color` in spectrogram style configuration
- Default channel colors updated (`#4799e8`, `#b775ff`)
- Triphase amplitude panel scaled to +6 dB (linear 2.0) to reflect the analog summation range
- Video export default CRF changed from 26 to 22, preset from `slow` to `medium`
- FFmpeg concat step now filters out codec-specific args when stream-copying segments
- Font rendering uses explicit font properties throughout for consistent cross-platform text appearance
- Reworked most video configuration profiles to improve processing speed and consistency of quality
- Switched audio playback dependency from `pygame` to `pygame-ce` (community edition)
- File selection dialogs now use Qt (`QFileDialog`) instead of tkinter, removing the tkinter dependency
- Player controls reordered: playback | repeat | fullscreen | playlist | stretch | oscilloscope | zoom | volume | triphase
- Repeat config changed from boolean to string enum (`none`/`one`/`all`) with backward compatibility for boolean values
- End-of-track handling now respects repeat mode: `one` loops the current file, `all` wraps around the playlist, `none` advances or stops
- Refactored `visualization.py` into a `visualization/` subpackage with separate modules: `base.py` (static images), `video.py` (direct render pipeline), `oscilloscope.py` (waveform overlay mixin)
- Font face index for TTC files now stored as derived config key (`visualization.style.font.text.face-index`) instead of a module-level variable

### Removed
- Removed `estimpy-visualizer` and `estimpy-player` CLI entry points, replaced by unified `estimpy` command
- Removed `-i`/`--input-files` flag (replaced by positional file arguments)
- Removed shorthand flags (`-si`, `-wi`, `-wv`, `-wm`, `-drange`, `-fmin`, `-fmax`, `-rf`, `-rs`)
- Removed legacy matplotlib-based interactive player (`VideoPlayerVisualization`), fully replaced by the Qt-based player
- Removed tkinter dependency (file dialogs replaced with Qt)

### Fixed
- Fixed MP4/M4A title metadata tag (`\xa9nam2` → `\xa9nam`) that silently prevented reading/writing titles
- Fixed orphaned spinner threads when audio file loading fails (e.g., non-audio files like Thumbs.db)
- Fixed player crash on startup caused by oscilloscope state accessed before initialization
- Pause/unpause no longer resets playback position (audio time is now captured before pausing)
- Volume step of zero no longer causes infinite loop in volume ramping
- Seeking to negative time values is now clamped to zero
- NFFT size now scales proportionally with window size when audio is resampled, preventing excessive zero-padding
- Audio pops eliminated: all volume transitions (increase, decrease, pause, unpause, stop, play, file switch) use smooth ramps instead of abrupt changes, with a synchronous 100ms fade-to-zero for stop and pause operations
- Volume no longer decays on rapid seeking (target volumes from Player state are used instead of intermediate ramp values)
- Per-channel volume controls now rebuild correctly when switching between files with different channel counts
- Channel volume and mute state lists now resize when switching between files with different channel counts
- Scrub bar position line no longer leaves a ghost artifact when zoom level is changed during playback
- Zoom level is now preserved when switching between files in the playlist
- `Audio.resample()` now passes audio data to the resample function (was missing first argument) and updates `sample_count` after resampling
- Metadata failures during video export now produce a warning instead of discarding the encoded video
- LICENSE file updated from GPL-3.0 to MIT to match pyproject.toml declaration

## [1.1.3] - 2026-02-10
### Removed
- Removed `flatdict` package requirement in favor of a custom implementation

### Added
- Updated `.gitignore` to include `.venv/` for virtual environment files
- Added installation instructions for `tkinter` on Mac and Linux in the README

## [1.1.2] - 2025-01-26
### Changed
- Changed batched file handling
  - Batch will continue processing additional files even if one or more files fail
  - List of files will always be processed in alphabetical order

### Fixed
- Fixed metadata handling bug

## [1.1.1] - 2025-01-19
### Added
- Added `--version` command-line argument to display package version information

### Fixed
- Fixed bug when writing video with apostrophe in file name

## [1.1.0] - 2025-01-04
### Added
- Added package installation support using `pip` 
- `estimpy` added to PyPI

### Changed
- Renamed project from `EstimPy` to `estimpy` (EstimPy will remain the preferred stylized name)
- Renamed front-end scripts and moved within package subdirectory:
  - `visualizer.py` → `estimpy/cli_visualizer.py`
  - `player.py` → `estimpy/cli_player.py`
- Updated CLI entry points to reflect the new names:
  - `estimpy-visualizer` now points to `visualizer_cli:main`.
  - `estimpy-player` now points to `player_cli:main`.
- Converted project specification from `setup.py` to `pyproject.toml`

### Removed
- Removed redundant `requirements.txt`

## [1.0.0] - 2025-01-01 (Happy New Year!)
### Added
- Handling for validating output files and overwriting existing files
- Support to override any configuration option from the command line
- Support to limit length of encoded video
- Optimized configuration profile for CD028 player

### Changed
- Improved user feedback during processing (Thanks @backslash167!)
- Enhanced readability of axes and time text
- Refactored channel style and display window length configuration

### Fixed
- Bug where album art metadata couldn't be written to audio files without an ID3 tag (Fixes #2. Thanks @JoostvL!)
- Bug where requested resolution would not be respected for interactive visualizations on high DPI displays 

## [0.1.1] - 2024-11-24
### Added
- Support for Python 3.13 (Thanks u/harrie27!)

### Changed
- Major rewrite of video export functionality. Significant improvements in encoding time and output file size.
- Specified Python version requirement >= 3.11

## [0.1.0] - 2024-11-18
Initial pre-release