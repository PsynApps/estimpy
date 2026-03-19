# Changelog

## [2.0.0] - 2026-03-18
### Added
- Unified `estimpy` CLI replacing `estimpy-visualizer` and `estimpy-player` with subcommands: `play` (default), `show-image`, `save-image`, `save-video`, `save-audio`, `save-metadata`, `benchmark`
- Positional file arguments (e.g., `estimpy play song.mp3`)
- Qt-based interactive player with real-time animated visualization, replacing the matplotlib-only player
- Direct frame rendering pipeline for video export, bypassing matplotlib's animation framework and piping raw frames to FFmpeg
- Reassigned spectrogram algorithm for sharper time-frequency localization, with configurable smoothing
- Triphase visualization mode (`-t`/`--triphase`) showing the derived common electrode signal -(A+B) alongside A and B channels, with per-mode config keys defaulting to off for images and on for video; instant toggle in the player UI
- Per-channel colormap derivation from a single base colormap, with automatic recoloring to match each channel's color using perceptual brightness matching (Rec. 709 relative luminance)
- Oscilloscope waveform overlay for video display and export with trigger-stabilized rendering, automatic tone/pulse detection (coefficient of variation analysis), real-time readouts (window length, peak frequency, signal level), configurable trigger correlation threshold, and manual duration controls in the player
- Configurable channel identity labels (A, B, T) centered across each channel's amplitude and spectrogram panels
- Stereo stim mode (`-ss`/`--stereo-stim`) applying a safety bandpass filter to remove DC offset, subsonic content, and high-frequency artifacts, with SS badge overlay on exported videos, player toggle (S key), and automatic audio re-encoding during video export
- Amplitude ramp (`audio.ramp.level`, `audio.ramp.shape`) that gradually increases audio amplitude from a reduced level to full over the file duration, with configurable exponential easing; available as a real-time player control (G key)
- Frequency transform (`audio.frequency.scale`, `audio.frequency.shift`) for shifting and/or scaling audio frequency content while preserving duration
- `save-audio` CLI command for exporting processed audio with the full processing chain applied, automatic format detection from output extension or source codec, visualization album art generation, and metadata embedding
- Audio export config profiles: `audio-mp3` (highest quality VBR), `audio-wav` (24-bit PCM), `audio-flac` (lossless)
- Container-aware video audio encoding: incompatible codecs (e.g., FLAC in MP4) are automatically re-encoded as AAC; compatible audio is stream-copied
- FLAC and MOV metadata support (read/write via mutagen)
- Player features: per-channel volume with colored tints, playlist management (add/remove/reorder, M3U import/export), repeat mode (none/one/all), fullscreen, zoom, keyboard shortcuts, smooth volume ramping on all transitions
- Player respects CLI audio processing parameters on load (frequency transform, ramp, stereo stim)
- Resolution-aware FFT sizing using coarse frequency pre-analysis and output panel dimensions
- User configuration directory (`~/.estimpy/`) for personal profile overrides
- Composable configuration via `additional-config-profiles` with cycle detection
- `estimpy-version` key in profiles for forward-compatible version identification
- `benchmark` subcommand for comparing video encoding profiles
- Configuration profiles for HEVC and ProRes VideoToolbox hardware encoding, and iPod Touch player
- Profiling mode for video export (`-p`/`--profiling`)
- Configurable time text position (`top`/`bottom`)
- Automated test suite (359 tests) covering audio, analysis, configuration, CLI, metadata, export, player, visualization, and utilities

### Changed
- Video encoding config keys moved from `visualization.video.export.*` to `video.export.*` (codec, format, fps, segment-length, etc.); visualization-appearance keys remain under `visualization.video.export.*`
- Audio processing chain reordered: frequency transform → ramp → stereo stim → triphase (stereo stim is always the last safety step before triphase derivation)
- Audio data stored as float32 (halved memory); spectrogram uses float32/complex64 throughout
- Reassigned spectrogram computed in chunks to limit peak memory; raw audio reconstructed on demand
- Default FFT length automatically sized based on output resolution and frequency content
- Default window overlap increased to 75% for better temporal resolution
- Envelope computation and spectral edge frequency vectorized for faster loading
- Spectrogram colormap simplified to a single base colormap with automatic per-channel derivation
- Channel identity (color, label, inverted) promoted to `visualization.style.channels.chN` with per-channel amplitude styling falling back to channel color
- Per-channel vertical inversion now configurable (previously ch1 was always inverted in stereo)
- Renamed `base-color` → `peak-color`, `match-amplitude-color` → `match-channel-color`
- Default channel colors updated; triphase amplitude panel scaled to +6 dB
- Video export default CRF 26 → 22, preset `slow` → `medium`; reworked encoding profiles
- Switched audio playback from `pygame` to `pygame-ce`; file dialogs from tkinter to Qt
- Player controls restructured into two-row layout: playback on the left spanning both rows, volume/ramp controls on top-right, toggle controls (triphase, SS, zoom, oscilloscope) on bottom-right
- Player window auto-sizes to tightly bound the visualization canvas at the configured aspect ratio, constrained to screen dimensions
- Repeat config changed from boolean to enum (`none`/`one`/`all`) with end-of-track handling per mode
- Refactored `visualization.py` into `visualization/` subpackage: `base.py`, `video.py`, `oscilloscope.py`
- `write_video()` returns a result dict with encoding statistics instead of a plain file path
- Audio export format auto-detected from output extension or source codec; explicit config overrides
- Font rendering uses explicit font properties for consistent cross-platform appearance

### Removed
- Removed `estimpy-visualizer` and `estimpy-player` CLI entry points, replaced by unified `estimpy` command
- Removed `-i`/`--input-files` flag (replaced by positional file arguments)
- Removed all v1.x shorthand and deprecated flags (`-si`, `-wi`, `-wv`, `-wm`, `-drange`, `-fmin`, `-fmax`, `-rf`, `-rs`, `--dynamic-range`, `--frequency-min`, `--frequency-max`)
- Removed legacy matplotlib-based interactive player, fully replaced by Qt-based player
- Removed tkinter dependency (file dialogs replaced with Qt)

### Fixed
- Fixed time position line z-order so it renders behind axes text, time text, channel labels, and oscilloscope overlays
- Fixed oscilloscope label font scaling at low export DPI (labels were rendering at 1px; now correctly scale with output resolution)
- Fixed silent exit when input files don't exist — CLI now reports an error message for each unmatched pattern
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