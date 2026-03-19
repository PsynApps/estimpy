# EstimPy

**EstimPy** is a Python library that generates visualizations of Estim audio files.

<div align="center">
<a href="https://youtu.be/T0NwOUIXx0A" target="_blank"><img src="https://github.com/user-attachments/assets/d71ad527-e206-498c-9de6-8fec1453a808"></a> 
</div>

## Table of Contents
- [Motivation](#motivation)
- [Features](#features)
- [Disclaimer](#disclaimer)
- [Visualization examples](#visualization-examples)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)

## Motivation

Estim is a hobby that uses specialized signal generators to produce powerful sensations. Many commercial units accept custom stimulation signals via audio input, and the enthusiast community has built a large library of custom sessions distributed as standard audio files. While this format is convenient and non-proprietary, it provides no way to understand the flow, intensity, or texture of a session before using it.

**EstimPy** solves this by generating rich visualizations from audio data — per-channel amplitude envelopes and spectrograms that make the structure of a session immediately visible. In video form, the visualization shows what is coming which can be useful during play and entertaining for others to watch and understand what is happening to the user.

## Features

### Interactive player
A Qt-based audio player with real-time animated visualization, designed for use with estim devices.
- **Per-channel volume control** with independent gain sliders and mute toggles
- **Smooth intensity transitions** — all volume changes (start, pause, seek, slider adjustment) ramp smoothly to prevent sudden changes in output intensity
- **Oscilloscope overlay** — per-channel waveform display with trigger-stabilized rendering, automatic tone/pulse detection, and real-time readout labels (window length, peak frequency, signal level)
- **Triphase toggle** — switch between stereo and 3-channel triphase visualization
- **Stereo stim toggle** — apply or remove safety bandpass filtering during playback
- **Amplitude ramp** — start a gradual amplitude ramp during playback with adjustable level and curve shape
- **Playlist management** — add, remove, reorder, and select files; drag-and-drop support; M3U import/export
- **Keyboard shortcuts** for all controls; fullscreen mode; click-to-seek on visualization panels

### Visualization
Per-channel analysis panels rendered for both static images and animated video:
- **Amplitude envelopes** — peak and RMS envelopes showing how intensity changes over time
- **Spectrogram** — frequency content with reassigned spectrogram for sharper time-frequency localization
- **Triphase mode** — derives and visualizes the common electrode signal -(A+B) for 3-electrode setups
- **Per-channel colormaps** — automatically recolors the base colormap to match each channel's identity color
- **Configurable styling** — colors, fonts, panel ratios, dynamic range, frequency bounds, axis visibility, and more

### Export
- **Video export** — animated sliding visualization rendered via a direct pixel pipeline and encoded with FFmpeg. Supports hardware-accelerated codecs, configurable resolution up to 8K, 120fps, segment-based encoding with resume, and preview frames with fade transitions.
- **Image export** — static full-file visualization saved as PNG or embedded as album art in audio file metadata (MP3, MP4, M4A, MOV, FLAC). Album art doubles as a visual navigation aid in media players.
- **Audio export** — re-encode audio with the full processing chain applied (frequency transform, ramp, stereo stim). Output format is autodetected from the file extension or matches the input. Generates a visualization image and embeds it as album art with metadata tags. Included profiles for MP3, WAV, and FLAC export.

### Audio processing
- **Frequency transform** — shift and/or scale frequency content while preserving duration. Scale multiplies all frequencies (preserving harmonics); shift adds a constant offset in Hz (changing intervals). Both can be combined.
- **Stereo stim filtering** — bandpass safety filter (default 20 Hz–12 kHz) for direct-output stereostim devices, removing DC offset, subsonic content, and high-frequency content.
- **Amplitude ramp** — gradually increases amplitude from a reduced level at the start of the file to full amplitude at the end, with configurable reduction level and exponential curve shape.

### Configuration
- YAML-based configuration system with composable profiles and per-key CLI overrides
- Included profiles for video codecs (HEVC, AV1, VP9, ProRes), resolutions (4K, 8K), frame rates (60/120fps), audio formats (MP3, WAV, FLAC), and player device presets
- User configuration directory (`~/.estimpy/`) for persistent customization
- Benchmark command for comparing video encoding performance across profiles

## Disclaimer

**EstimPy** is provided on an **experimental basis**, and it should **not** be assumed to be safe or fully functional. **Estim (electrical stimulation)** can be dangerous if proper safety precautions are not followed or if unreliable equipment is used. This package is offered strictly for experimental and research purposes. The creators of this package assume **no responsibility** for any adverse effects, injury, or harm that may result from the use of EstimPy or any Estim-related activities.

## Visualization examples

### Layout

Each channel of audio is visualized with two panels:
- **Amplitude envelope** — peak (behind) and RMS (foreground), scaled from -∞ to 0 dB
- **Spectrogram** — 90 dB dynamic range, autodetected frequency ceiling

#### 1-channel (mono) audio file ####
<p align="center">
  <img src="https://github.com/user-attachments/assets/d575237b-583b-4181-afcd-46e888a311af" width="480">
</p>

#### 2-channel (stereo) audio file ####
<p align="center">
  <img src="https://github.com/user-attachments/assets/9fa6770a-ed43-4a7e-ab77-ba84a58c2220" width="480">
</p>

---
## Getting started

### System requirements

**EstimPy** requires that **FFmpeg** and **FFprobe** are installed and accessible via your system's PATH. If you would like to use alternative codecs, FFmpeg must also be built with those libraries (e.g. libaom-av1).

#### Installing FFmpeg and FFprobe

##### Windows

- Download the FFmpeg executable from the [FFmpeg official website](https://ffmpeg.org/download.html)
- Extract the downloaded archive to a directory of your choice (e.g., `C:\ffmpeg\`)
- Add the `bin` directory to your system’s PATH:
  - Open **System Properties > Advanced > Environment Variables**
  - Under **System variables**, select **Path** and click **Edit**
  - Click **New** and add the path to the `bin` folder (e.g., `C:\ffmpeg\bin\`)

##### MacOS

- Install **FFmpeg** and **FFprobe** using Homebrew:
  ```
  brew install ffmpeg
  ```
  
##### Linux (Ubuntu/Debian)

- Install **FFmpeg** and **FFprobe** using the package manager:
  ```
  sudo apt update
  sudo apt install ffmpeg
  ```

##### Verifying FFmpeg installation

After installing FFmpeg and FFprobe, ensure they are accessible via your system's PATH by running the following commands in your terminal:
```
ffmpeg -version
ffprobe -version
```

Both commands should return the version of FFmpeg/FFprobe that is installed.
### Installation

#### Installing the latest stable release

You can install the latest stable release of **EstimPy** directly from PyPI using:
```
pip install estimpy
```

#### Installing the latest development version

To install the latest development version (which may be unstable), use the following:
```
git clone https://github.com/PsynApps/estimpy.git
cd estimpy
```

To install the package for basic usage:
```
pip install .
```

For development purposes, you can also install the package in editable mode:
```
pip install -e .
```

#### Windows installation error

On Windows, you may get an error like: ```Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools"```. This error occurs when you are using the latest version of python because prebuilt package wheels are only included for earlier versions of Python. To fix this, you can either:
* Install the ["C++ development tools"](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (requires ~9 GB) from Microsoft Visual Studio
* Downgrade your python version by one minor revision (e.g. 3.12 when 3.13 is the latest minor release)

## Usage

EstimPy provides a unified command-line interface for visualization and playback.

```
estimpy [command] [files...] [options]
```

If no command is given, the player is launched. If no files are given, a file dialog will prompt for file selection.

### Commands

| Command           | Description                                                                                                        |
|-------------------|--------------------------------------------------------------------------------------------------------------------|
| `play`            | Launch the interactive player (default if no command is given)                                                      |
| `show-image`      | Display an interactive window with the image visualization of the input file(s)                                    |
| `save-image`      | Save an image file with visualization of the input file(s). Output uses the same base name as the input file.      |
| `save-video`      | Save a video file with an animated visualization. Output uses the input file as the audio track.                   |
| `save-audio`      | Save processed audio file(s) with the audio processing chain applied (frequency transform, amplitude ramp, stereo stim). Output format is autodetected from the `-o` file extension or matches the input format. Generates a visualization image and embeds it as album art along with metadata tags. |
| `save-metadata`   | Write the image visualization as album art to the audio file metadata. Supported for MP3, MP4, M4A, MOV, and FLAC files. |
| `benchmark`       | Benchmark video encoding across all video profiles and display a comparison table of performance and file size. Supports `-o` to keep encoded files (named `benchmark-YYYYMMDDHHMMSS-profile.ext`) and `-c` to benchmark a specific combination of profiles instead of all video profiles (the `video-` prefix may be omitted). |

### Global options

| Option                                             | Description                                                                                                            |
|----------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| `-h`, `--help`                                     | Show the help message and exit.                                                                                        |
| `--version`                                        | Display version information and exit.                                                                                  |
| `-t`, `--triphase`                                 | Visualize stereo audio as 3 channels: A, B, and the triphase signal -(A+B) at the common electrode.                   |
| `-r`, `--recursive`                                | Load input files recursively from the specified directories.                                                           |
| `-c PROFILE [...]`, `--config`                     | Apply additional configuration profile(s).                                                                             |
| `-co K V [...]`, `--config-option`                 | Override specific configuration option(s).                                                                             |
| `-col`, `--config-option-list`                     | List all configuration options and their current values and exit.                                                      |
| `-ss`, `--stereo-stim`                 | Apply stereo stim filters (bandpass 20 Hz–12 kHz) for safer use with direct-output stereostim devices.      |

### Save options

These options are available on `save-image`, `save-audio`, `save-video`, and `save-metadata`:

| Option                                 | Description                                                                                            |
|----------------------------------------|--------------------------------------------------------------------------------------------------------|
| `-o PATH`, `--output-path`             | Path to save output file(s). If not specified, uses the current directory.                             |
| `-y`, `--yes`                          | Answers yes to all interactive prompts (overwrites existing output files by default).                  |

### Save-video options

These options are only available on `save-video`:

| Option                                 | Description                                                                                            |
|----------------------------------------|--------------------------------------------------------------------------------------------------------|
| `--resume-frame N`                     | Frame on which to resume video encoding (useful for resuming if encoding crashes).                     |
| `--resume-segment N`                   | Segment on which to resume video encoding (useful for resuming if encoding crashes).                   |
| `-p`, `--profiling`                    | Enable profiling output for video export. Prints per-frame timing breakdown to stdout.                 |

### Examples

- **Launch the player with an audio file**
  ```
  estimpy input.mp3
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/d67fde73-db40-492d-bc82-bcb21da8bcef" width="720">
</p>

- **Launch the player with multiple files as a playlist**
  ```
  estimpy input1.mp3 input2.mp3 input3.mp3
  ```

- **Show image visualization interactively**
  ```
  estimpy show-image input.mp3
  ```

<p align="center">
  <img src="https://github.com/user-attachments/assets/8e6d3767-387c-450e-bd31-83aecbe2a2fc" width="480">
</p>

- **Save image visualization to an image file**
  ```
  estimpy save-image input.mp3
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/9fa6770a-ed43-4a7e-ab77-ba84a58c2220" width="480">
</p>

- **Save image visualization to the metadata of an audio file**
  ```
  estimpy save-metadata input.mp3
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/b976c3da-815a-4a8b-ba3b-66fbac5867fc" width="480">
</p>

- **Save image visualization to the metadata of all supported files in a path recursively**
  ```
  estimpy save-metadata ../library/* -r
  ```

- **Save processed audio with stereo stim filtering applied** (output matches input format)
  ```
  estimpy save-audio input.mp3 -ss
  ```

- **Save processed audio as FLAC with amplitude ramp** (using config profile)
  ```
  estimpy save-audio input.mp3 -c audio-flac -co audio.ramp.level 50
  ```

- **Double, then shift all frequencies up by 250 Hz and apply stereostim processing**
  ```
  estimpy save-audio input.mp3 -ss -co audio.frequency.scale 2 audio.frequency.shift 250
  ```

- **Save animated visualization to a video file**
  ```
  estimpy save-video input.mp3
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/d71ad527-e206-498c-9de6-8fec1453a808">
</p>

- **Save animated visualization to a 8k 60fps video file**
  ```
  estimpy save-video input.mp3 -c video-8k video-60fps
  ```
  **<a href="https://youtu.be/T0NwOUIXx0A" target="_blank">Example high-resolution video (via YouTube)</a>**

- **Benchmark all video encoding profiles**
  ```
  estimpy benchmark
  ```

- **Benchmark with a custom audio file and keep the encoded files**
  ```
  estimpy benchmark input.mp3 -o ./benchmark-output
  ```

- **Benchmark a specific combination of profiles** (the `video-` prefix is optional)
  ```
  estimpy benchmark -c hevc_videotoolbox 8k 60fps
  ```

## Configuration

EstimPy uses a YAML-based configuration system to define its behavior. Configuration variables are initialized with the values specified in `config/default.yaml` from the python package directory.

EstimPy's command-line scripts support loading additional configuration profiles to override default values. Several additional configuration profiles are included in the EstimPy package in the `config/` subdirectory for common scenarios where alternative settings would be preferred.

When specifying one or more built-in configuration profiles using the `--config` option of the command line scripts, it is not necessary to specify the path or the `.yaml` file extension.

### Additional configuration profiles

The following additional configuration profiles are included with **EstimPy**:

| Profile Name         | Description                                                    |
|----------------------|----------------------------------------------------------------|
| `default`            | The default base configuration (loaded automatically)          |
| `audio-mp3`                 | Export audio as MP3 (highest quality VBR)                            |
| `audio-flac`                | Export audio as FLAC (lossless)                                      |
| `audio-wav`                 | Export audio as WAV (24-bit PCM, lossless)                           |
| `image-4k-square`           | Generate image visualization in 4K with a square aspect ratio        |
| `image-8k-square`           | Generate image visualization in 8K with a square aspect ratio        |
| `image-videopreview`        | Generate image visualization in 1440p with a 16:9 aspect ratio       |
| `notitle`                   | Remove the title panel from all visualizations                       |
| `player-cd028`              | Optimized settings for the CD-028 player                             |
| `player-galaxytabs10ultra`  | Optimized settings for the Galaxy Tab S10 Ultra player               |
| `player-ipodtouch`          | Optimized settings for the iPod Touch player                         |
| `video-4k`                  | Generate animated visualizations in 4K                               |
| `video-8k`                  | Generate animated visualizations in 8K                               |
| `video-60fps`               | Generate animated visualizations in 60fps                            |
| `video-120fps`              | Generate animated visualizations in 120fps                           |
| `video-av1`                 | Encode video with AV1 codec using CPU                                |
| `video-av1_nvenc`           | Encode video with AV1 encoding using NVENC hardware                  |
| `video-hevc_nvenc`          | Encode video with HEVC encoding using NVENC hardware                 |
| `video-hevc_videotoolbox`   | Encode video with HEVC encoding using VideoToolbox hardware (macOS)  |
| `video-prores_videotoolbox` | Encode video with ProRes codec using VideoToolbox hardware (macOS)   |
| `video-vp9`                 | Encode video with VP9 codec using CPU                                |

### User configuration directory

EstimPy also searches `~/.estimpy/` for configuration profiles. When a profile name is loaded (via `--config` or `additional-config-profiles`), the builtin version is loaded first, then any user version of the same name is loaded as an overlay. This allows you to customize builtin profiles without modifying the package files.

User-only profiles (with no builtin counterpart) are also supported and can be loaded with `--config`.

For example, creating `~/.estimpy/default.yaml` with the following content would automatically apply the HEVC VideoToolbox codec profile on every run:

```yaml
additional-config-profiles:
  - hevc_videotoolbox
```

### Profile keys

All configuration profiles support these top-level keys:

| Key                            | Description                                                                                     |
|--------------------------------|-------------------------------------------------------------------------------------------------|
| `estimpy-version`              | The estimpy version the profile is designed for. A warning is shown if the profile targets a newer version than the running installation. |
| `additional-config-profiles`   | A list of profile names to load after the current profile. Enables composable configuration chains. |

### Creating custom configuration files

The best way to create a custom configuration profile to ensure it follows the correct schema is to:
1. Copy `config/default.yaml` to the new file destination
2. Remove the configuration options you don't wish to change
3. Edit the values of the remaining options and save the file

You can then apply your configuration using the `--config` command-line option:
```
estimpy <command> [files...] --config path_to/config_file.yaml
```

Custom profiles can also be placed in `~/.estimpy/` to be loadable by name without specifying a path.

### Overwriting configuration option values

Specific configuration option values can also be overwritten at runtime using the `--config-option` command-line argument.
A list of options and their current values can be shown using the `--config-option-list` command-line argument.
If additional configuration profiles have been loaded, any updated values will be reflected in the list.

For reference, the default configuration options and values are as follows:

| Configuration Option                                         | Value                                        |
|--------------------------------------------------------------|----------------------------------------------|
| audio.export.codec                                           | None (auto)                                  |
| audio.export.format                                          | None (auto)                                  |
| audio.export.sample-rate                                     | None                                         |
| audio.frequency.scale                                        | 1                                            |
| audio.frequency.shift                                        | 0                                            |
| audio.ramp.level                                             | 0                                            |
| audio.ramp.shape                                             | 0                                            |
| audio.stereo-stim.enabled                         | False                                        |
| audio.stereo-stim.high-pass                       | 20                                           |
| audio.stereo-stim.low-pass                        | 12000                                        |
| analysis.oscilloscope.pulse-detection.count-threshold        | 5                                            |
| analysis.oscilloscope.pulse-detection.cv-threshold           | 1.5                                          |
| analysis.oscilloscope.pulse-detection.enabled                | True                                         |
| analysis.oscilloscope.pulse-detection.window-length          | 500                                          |
| analysis.oscilloscope.silence-threshold                      | 0.01                                         |
| analysis.oscilloscope.trigger-correlation-threshold          | 0.3                                          |
| analysis.oscilloscope.trigger-hysteresis                     | 0.05                                         |
| analysis.oscilloscope.window-length                          | 10                                           |
| analysis.spectrogram.frequency-min                           | 0                                            |
| analysis.spectrogram.frequency-max                           | None                                         |
| analysis.spectrogram.frequency-max-method                    | spectral_edge                                |
| analysis.spectrogram.frequency-max-padding-factor            | 1.1                                          |
| analysis.spectrogram.nfft                                    | None                                         |
| analysis.spectrogram.reassign                                | True                                         |
| analysis.spectrogram.reassign-smoothing                      | 1.0                                          |
| analysis.spectrogram.window-function                         | hann                                         |
| analysis.window-size                                         | 2048                                         |
| analysis.window-overlap                                      | None                                         |
| estimpy-version                                              | 2.0.0                                        |
| files.input.recursive                                        | False                                        |
| files.output.path                                            | ./                                           |
| files.output.overwrite-default                               | False                                        |
| files.output.overwrite-prompt                                | True                                         |
| metadata.default-genre                                       | Estim                                        |
| metadata.file-path-pattern                                   | (?P<artist>[^\\\/]*?) - (?P<title>.*)        |
| player.autoplay                                              | False                                        |
| player.spectrogram-reassign                                  | False                                        |
| player.repeat                                                | none                                         |
| player.skip-length                                           | 60                                           |
| player.video-render-latency                                  | 0.5                                          |
| player.volume-start                                          | 50                                           |
| player.volume-step                                           | 1                                            |
| player.volume-ramp-min-length                                | 1                                            |
| player.volume-ramp-max-length                                | 5                                            |
| visualization.image.display.size                             | 1080x1080                                    |
| visualization.image.display.time.enabled                     | True                                         |
| visualization.image.display.time.position                    | bottom                                       |
| visualization.image.display.title.enabled                    | False                                        |
| visualization.image.display.triphase                         | False                                        |
| visualization.image.export.format                            | png                                          |
| visualization.image.export.size                              | 1080x1080                                    |
| visualization.image.export.time.enabled                      | True                                         |
| visualization.image.export.time.position                     | bottom                                       |
| visualization.image.export.title.enabled                     | True                                         |
| visualization.image.export.triphase                          | False                                        |
| visualization.style.amplitude.channels.ch0.background-color  | None                                         |
| visualization.style.amplitude.channels.ch0.peak-color        | None                                         |
| visualization.style.amplitude.channels.ch0.rms-color         | None                                         |
| visualization.style.amplitude.channels.ch1.background-color  | None                                         |
| visualization.style.amplitude.channels.ch1.peak-color        | None                                         |
| visualization.style.amplitude.channels.ch1.rms-color         | None                                         |
| visualization.style.amplitude.channels.ch2.background-color  | None                                         |
| visualization.style.amplitude.channels.ch2.peak-color        | None                                         |
| visualization.style.amplitude.channels.ch2.rms-color         | None                                         |
| visualization.style.amplitude.axes.enabled                   | True                                         |
| visualization.style.amplitude.background-alpha               | 0.15                                         |
| visualization.style.amplitude.padding                        | 0.1                                          |
| visualization.style.amplitude.rms-alpha                      | 0.5                                          |
| visualization.style.amplitude.show-rms                       | True                                         |
| visualization.style.channels.ch0.color                       | #4799e8                                      |
| visualization.style.channels.ch0.inverted                    | False                                        |
| visualization.style.channels.ch0.label                       | A                                            |
| visualization.style.channels.ch1.color                       | #b775ff                                      |
| visualization.style.channels.ch1.inverted                    | False                                        |
| visualization.style.channels.ch1.label                       | B                                            |
| visualization.style.channels.ch2.color                       | #e06cb7                                      |
| visualization.style.channels.ch2.inverted                    | False                                        |
| visualization.style.channels.ch2.label                       | T                                            |
| visualization.style.channels.labels.enabled                  | True                                         |
| visualization.style.channels.labels.font-size                | 64                                           |
| visualization.style.axes.color                               | #ffffff                                      |
| visualization.style.axes.font-size                           | 16                                           |
| visualization.style.axes.text-padding                        | 1                                            |
| visualization.style.axes.tick-length                         | 5                                            |
| visualization.style.axes.tick-width                          | 1                                            |
| visualization.style.font.symbols.family                      | Segoe UI Symbol, DejaVu Sans                 |
| visualization.style.font.text.border-color                   | #000000                                      |
| visualization.style.font.text.border-width                   | 1                                            |
| visualization.style.font.text.family                         | Helvetica Neue, Helvetica, Arial, sans-serif |
| visualization.style.font.text.weight                         | bold                                         |
| visualization.style.oscilloscope.border-width                | 10                                           |
| visualization.style.oscilloscope.font-size                   | 12                                           |
| visualization.style.oscilloscope.height-ratio                | 0.5                                          |
| visualization.style.oscilloscope.line-width                  | 15                                           |
| visualization.style.oscilloscope.opacity                     | 0.95                                         |
| visualization.style.oscilloscope.width-ratio                 | 0.25                                         |
| visualization.style.spectrogram.color-map                    | jet                                          |
| visualization.style.spectrogram.match-channel-color          | True                                         |
| visualization.style.spectrogram.match-channel-color-radius   | 5                                            |
| visualization.style.spectrogram.channels.ch0.color-map       | None                                         |
| visualization.style.spectrogram.channels.ch1.color-map       | None                                         |
| visualization.style.spectrogram.channels.ch2.color-map       | None                                         |
| visualization.style.spectrogram.axes.enabled                 | True                                         |
| visualization.style.spectrogram.dynamic-range                | 90                                           |
| visualization.style.subplot-height-ratios.title              | 1                                            |
| visualization.style.subplot-height-ratios.amplitude.mono     | 3                                            |
| visualization.style.subplot-height-ratios.amplitude.stereo   | 1.25                                         |
| visualization.style.subplot-height-ratios.amplitude.triphase | 1.25                                         |
| visualization.style.subplot-height-ratios.spectrogram.mono   | 6                                            |
| visualization.style.subplot-height-ratios.spectrogram.stereo | 3.25                                         |
| visualization.style.subplot-height-ratios.spectrogram.triphase | 3.25                                       |
| visualization.style.time.font-size                           | 24                                           |
| visualization.style.title.background-color                   | #000000                                      |
| visualization.style.title.color                              | #ffffff                                      |
| visualization.style.title.font-size                          | 24                                           |
| visualization.style.title.width-factor-max                   | 0.9                                          |
| visualization.style.video.position-line-color                | #ffffff                                      |
| visualization.video.display.oscilloscope.enabled             | True                                         |
| visualization.video.display.oscilloscope.show-labels         | True                                         |
| visualization.video.display.size                             | 1920x1080                                    |
| visualization.video.display.time.enabled                     | False                                        |
| visualization.video.display.time.position                    | top                                          |
| visualization.video.display.title.enabled                    | False                                        |
| visualization.video.display.triphase                         | True                                         |
| visualization.video.display.window-length                    | 20                                           |
| video.export.codec                                           | libx265                                      |
| video.export.ffmpeg-extra-args.-hide_banner                  |                                              |
| video.export.ffmpeg-extra-args.-loglevel                     | error                                        |
| video.export.ffmpeg-extra-args.-y                            |                                              |
| video.export.ffmpeg-extra-args.-pix_fmt                      | yuv420p10le                                  |
| video.export.ffmpeg-extra-args.-colorspace                   | bt709                                        |
| video.export.ffmpeg-extra-args.-crf                          | 22                                           |
| video.export.ffmpeg-extra-args.-preset                       | medium                                       |
| video.export.ffmpeg-extra-args.-movflags                     | +faststart                                   |
| video.export.ffmpeg-extra-args.-tune                         | animation                                    |
| video.export.format                                          | mp4                                          |
| video.export.fps                                             | 30                                           |
| video.export.keyframe-interval                               | None                                         |
| video.export.preview.enabled                                 | True                                         |
| video.export.preview.length                                  | 2                                            |
| video.export.preview.fade-length                             | 1                                            |
| video.export.reencode-segments                               | False                                        |
| video.export.segment-length                                  | 3600                                         |
| video.export.video-length-max                                | None                                         |
| visualization.video.export.oscilloscope.enabled              | True                                         |
| visualization.video.export.oscilloscope.show-labels          | True                                         |
| visualization.video.export.size                              | 1920x1080                                    |
| visualization.video.export.time.enabled                      | True                                         |
| visualization.video.export.time.position                     | top                                          |
| visualization.video.export.title.enabled                     | False                                        |
| visualization.video.export.triphase                          | True                                         |
| visualization.video.export.window-length                     | 20                                           |

## Development

### Regenerating the benchmark file

The `benchmark` command uses `tests/input/benchmark.mp3` as its default input file. This file is generated from source audio files using a script that analyzes the audio content and selects diverse segments spanning a range of amplitude, frequency, and modulation characteristics. Mono sources are automatically duplicated to stereo when mixed with stereo sources.

To regenerate the benchmark file:

1. Place estim audio files in `tests/input/benchmark/`
2. Run the generator script:
   ```
   python tests/generate_benchmark.py
   ```

The script prompts before overwriting an existing output file. Output length, segment length, and output path are configurable:

```
python tests/generate_benchmark.py --output-length 120 --segment-length 10 --output custom.mp3
```

Each source file is guaranteed at least one segment in the output (when slots permit). The script analyzes candidate segments, filters out silence and section transitions, then uses farthest-first traversal in feature space to select segments that maximize diversity across RMS amplitude, spectral centroid, spectral bandwidth, and amplitude modulation depth.

### Running tests

```
pytest tests/
```
