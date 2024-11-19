
# EstimPy

**EstimPy** is a Python library that generates visualizations of Estim audio files.

<p align="center">
  <a href="https://youtu.be/7zNsNnao8KU" target="_blank"><img src="https://github.com/user-attachments/assets/4a117a9a-d802-4c1e-a0e2-9471290d4ece"></a>
</p>

## Motivation

Estim is a hobby which uses specialized signal generators to produce powerful sensations which can be pleasurable or painful depending on the intensity and characteristics of the stimulation signal delivered. The perception of these signals varies widely across individuals, so many hobbyists have to experiment with a range of devices, patterns, and intensities of stimulation to match their preferences.

Many commercial Estim units support custom stimulation signals using audio input in addition to an included small library of simple stimulation patterns. Over time, the Estim enthusiast community has created a large repository of custom sessions distributed as basic audio files. While this format is convenient because it is non-proprietary and easy to use, it does not provide an easy mechanism to understand the nuances of a session.

EstimPy helps users understand the flow, intensity, and texture of Estim audio sessions by generating intuitive visualizations from the audio data.

---

## Features
- **Visualization analyses**: Visualizations are generated for each channel of audio data
  - **Amplitude Envelopes**: Generates peak and RMS amplitude envelopes, showing how intensity changes over time
  - **Spectrogram**: Visualizes the frequency content of the audio, showing how texture changes over time
- **Image visualization**: Generates a single-image visualization of a full audio file
  - **Image file export**: Image visualization can be saved to an image file
  - **Album art embedding**: Image visualization can be directly embedded in the metadata of the audio file
    - During playback, album art is often rendered at the same width as the time position slider. Using the image visualization as album art, the file can be easily navigated and upcoming changes in the session can be anticipated.
  - **Interactive display**: Image visualization can be rendered on an interactive plot to allow detailed inspection of the audio file
- **Animated visualization**: Generates an animated sliding visualization of the audio file
  - **Video file export**: Animated visualization can be saved to a video file
  - **Interactive player**: Animated visualization used within experimental audio file player
- **Audio player**: Plays estim audio files for use with stereostim devices (***HIGHLY EXPERIMENTAL!***)
  - **Real-time visualization**: Based on the animated visualization
  - **Separate channel output control**: Allows signal gain of each channel to be independently controlled
  - **Smooth intensity transitions**: Ensures that any changes in playback will transition smoothly to avoid sudden changes in output intensity
    - This only affects changes in playback caused by interacting with the player (i.e. start, unpause, relocate time position, amplitude adjustment)
    - This will NOT alter sudden changes which are encoded directly in the audio data
  - **Playlists**: Multiple files can be queued to play sequentially
- **Highly configurable**: Nearly all parameters related to the rendering and export of visualizations are determined from an easily customizable configuration file

---

## Disclaimer

**EstimPy** is provided on an **experimental basis**, and it should **not** be assumed to be safe or fully functional. **Estim (electrical stimulation)** can be dangerous if proper safety precautions are not followed or if unreliable equipment is used. This package is offered strictly for experimental and research purposes. The creators of this package assume **no responsibility** for any adverse effects, injury, or harm that may result from the use of EstimPy or any Estim-related activities.

---

## Visualization examples

### Default layout and behavior ###

<p align="center">
  <img src="https://github.com/user-attachments/assets/a771d406-79db-44bb-af82-31f1b9a8f641" width="1080">
</p>

Both image and animated visualizations use the same basic layout to visualize each channel of audio data
- Peak and RMS amplitude envelopes
  - The peak amplitude envelope is shown behind the RMS amplitude envelope
  - Envelope amplitude display range always spans from -Inf to 0 dB
- Spectrogram
  - The default dynamic range for all spectrograms is 90 dB
  - The minimum frequency displayed is 0
  - The maximum frequency displayed is autodetected (unless overridden)

#### 1-channel (mono) audio files ####
<p align="center">
  <img src="https://github.com/user-attachments/assets/633dbbba-2b6e-42dc-ad7d-86380e6e88c5" width="480">
</p>

#### 2-channel (stereo) audio files ####
<p align="center">
  <img src="https://github.com/user-attachments/assets/6943a433-4241-471d-9df5-bd151e76e6b9" width="480">
</p>

---
## Getting Started

### System requirements

**EstimPy** requires that **FFmpeg** and **FFprobe** are installed and accessible via your system’s PATH. If you would like to use alternative codecs, FFmpeg must also be built with those libraries (e.g. libaom-av1).

#### Installing FFmpeg and FFprobe

##### Windows

- Download the FFmpeg executable from the [FFmpeg official website](https://ffmpeg.org/download.html)
- Extract the downloaded archive to a directory of your choice (e.g., `C:\ffmpeg`)
- Add the bin` directory to your system’s PATH:
  - Open **System Properties > Advanced > Environment Variables**
  - Under **System variables**, select **Path** and click **Edit**
  - Click **New** and add the path to the bin folder (e.g., `C:\ffmpeg\bin`)

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

##### Verifying Installation

After installing FFmpeg and FFprobe, ensure they are accessible via your system's PATH by running the following commands in your terminal:

```
ffmpeg -version
ffprobe -version
```

Both commands should return the version of FFmpeg/FFprobe that is installed.
### Installation

To install **EstimPy**, you must clone the repository and install dependencies manually:

```
git clone https://github.com/PsynApps/EstimPy.git
cd EstimPy
pip install -r requirements.txt
```

---
## Usage

EstimPy provides two command-line tools for generating visualizations.

- `visualizer.py`: Generates image and video visualizations of Estim audio files
- `player.py`: Provides a highly experimental real-time player for Estim audio files

### `visualizer.py`

- `visualizer.py` performs one or more actions using one or more input files.
- Multiple actions can be performed in a single command, allowing for flexibility in generating visualizations, saving files, and embedding metadata. 
- If no input file is specified, a file dialog will be shown to allow you to select one or more input files.
- If no action is specified, the script will use the `show-image` action.

#### Basic usage
```
python visualizer.py [actions] [options]
```

#### Actions

| Action                                 | Description                                                                                                                                         |
|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| `-si`, `--show-image`                  | Display an interactive window with the image visualization of the input file(s). This is the default behavior if no action is specified.            |
| `-wi`, `--write-image`                 | Save an image file with visualizations of the input file(s). The output file will use the same base name as the input file.                         |
| `-wm`, `--write-metadata`              | Modify the input file(s) to add or replace the album art metadata with the image visualization. This is only supported for mp3, mp4, and m4a files. |
| `-wv`, `--write-video`                 | Save a video file with an animated visualization of the input file(s). The output file will use the input file as the audio track with base name.   |

Note: If multiple actions are specified, the order does not matter. Actions will always execute in the order of `write-image`, `write-metadata`, `write-video`, and `show-image`. 

#### Options

| Option                                     | Description                                                                                                            |
|--------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| `-h`, `--help`                             | Show the help message and exit.                                                                                        |
| `-i [INPUT_FILES ...]`, `--input-files`    | Input file(s). Supports wildcards for batch processing. If not provided, a file dialog will prompt for file selection. |
| `-r`, `--recursive`                        | Load input files recursively from the specified directories.                                                           |
| `-o OUTPUT_PATH`, `--output-path`          | Specify the path to save the output file(s). If not specified, files will be saved to the current path.                |
| `-c [CONFIG ...]`, `--config`              | Apply additional configuration file(s).                                                                                |
| `-drange DYNAMIC_RANGE`, `--dynamic-range` | Set the dynamic range (in decibels) for the spectrogram display.                                                       |
| `-fmin FREQUENCY_MIN`, `--frequency-min`   | Set the minimum frequency (in Hz) for the spectrogram display.                                                         |
| `-fmax FREQUENCY_MAX`, `--frequency-max`   | Set the maximum frequency (in Hz) for the spectrogram display. If not defined, it will be auto-scaled.                 |
| `-rf RESUME_FRAME`, `--resume-frame`       | Specify the frame on which to resume video encoding (useful for resuming if encoding crashes).                         |
| `-rs RESUME_SEGMENT`, `--resume-segment`   | Specify the segment on which to resume video encoding (useful for resuming if encoding crashes).                       |

#### Configuration

Many aspects of the visualization rendering and output can be customized using additional configuration files specified by the `--config` command-line option. See the Configuration section for more details.

#### Examples

- **Show image visualization interactively**
  ```
  python visualizer.py -si -i input.mp3
  ```

<p align="center">
  <img src="https://github.com/user-attachments/assets/8d40a223-c564-4ded-8c3c-07cf08afe253" width="480">
</p>

- **Save image visualization to an image file**
  ```
  python visualizer.py -wi -i input.mp3
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/dfe0465e-b4f4-4819-9af7-e7f4f84d5d8e" width="480">
</p>

- **Save image visualization to the metadata of all supported files in a path recursively**
  ```
  python visualizer.py -wm -i ../library/* -r
  ```

- **Save animated visualization to a 4k 60fps video file**
  ```
  python visualizer.py -wv -i input.mp3 -c video-4k video-60fps
  ```
<p align="center">
  <img src="https://github.com/user-attachments/assets/4a117a9a-d802-4c1e-a0e2-9471290d4ece">
</p>
  
- **Perform multiple actions in one command:**
  ```
  python visualizer.py -si -wi -wm -wv -i input.mp3
  ```
  This command will:
  - Save an image visualization to input.png
  - Embed the image visualization as album art in the metadata of input.mp3
  - Save an animated visualization to input.mp4
  - Display the image visualization interactively
    
### `player.py`

- `player.py` provides a real-time player for Estim audio files with an animated visualization
- Provides independent control of channel volume output. Changes in output levels are always gradually ramped to avoid sudden changes in stimulation level.
- If no input file is specified, a file dialog will be shown where one or more files can be selected.
- If multiple input files are specified, a playlist will be created, and files will be played in the specified order.

#### Basic usage
```
python player.py [options]
```

#### Options

| Option                                            | Description                                                                                                            |
|---------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| `-h`, `--help`                                    | Show the help message and exit.                                                                                        |
| `-i [INPUT_FILES ...]`, `--input-files`           | Input file(s). Supports wildcards for batch processing. If not provided, a file dialog will prompt for file selection. |
| `-r`, `--recursive`                               | Load input files recursively from the specified directories.                                                           |
| `-c [CONFIG ...]`, `--config`                     | Apply additional configuration file(s).                                                                                |
| `-drange DYNAMIC_RANGE`, `--dynamic-range`        | Set the dynamic range (in decibels) for the spectrogram display.                                                       |
| `-fmin FREQUENCY_MIN`, `--frequency-min`          | Set the minimum frequency (in Hz) for the spectrogram display.                                                         |
| `-fmax FREQUENCY_MAX`, `--frequency-max`          | Set the maximum frequency (in Hz) for the spectrogram display. If not defined, it will be auto-scaled.                 |

#### Examples

- Launch the player and load an Estim audio file:
  ```
  python player.py -i input.mp3
  ```
<p align="center">
  <a href="" target="_new"><img src="https://github.com/user-attachments/assets/c7ef7f1c-a118-4de3-bbc9-cd391eb1b004" width="720"></a>
</p>

- Launch the player and load multiple Estim audio files into a playlist:
  ```
  python player.py -i input1.mp3 input2.mp3 input3.mp3
  ```
  
## Configuration

EstimPy uses a YAML-based configuration system to define its behavior. Configuration variables are initialized with the values specified in `config/default.yaml` from the python package directory.

EstimPy's command-line scripts support loading additional configuration files to override default values. Several additional configuration files are also included in the EstimPy package for common scenarios where alternative settings would be preferred.

When specifying an additional configuration file using the `--config` option of the command line scripts, if the file is included with EstimPy (i.e., exists in the `config/` path of the package), it is not necessary to specify the path. It is also not necessary to specify the `.yaml` file extension

### Additional Configuration Files

The following additional configuration files are included with **EstimPy**:

| File Name                 | Description                                                    |
|---------------------------|----------------------------------------------------------------|
| `default.yaml`            | The default base configuration (loaded automatically)          |
| `image-4ksquare.yaml`     | Generate image visualization in 4K with a square aspect ratio  |
| `image-8ksquare.yaml`     | Generate image visualization in 8K with a square aspect ratio  |
| `image-videopreview.yaml` | Generate image visualization in 1440p with a 16:9 aspect ratio |
| `notitle.yaml`            | Remove the title panel from all visualizations                 |
| `video-4k.yaml`           | Generate animated visualizations in 4K                         |
| `video-8k.yaml`           | Generate animated visualizations in 8K                         |
| `video-60fps.yaml`        | Generate animated visualizations in 60fps                      |
| `video-120fps.yaml`       | Generate animated visualizations in 120fps                     |
| `video-av1.yaml`          | Encode video with AV1 codec using CPU                          |
| `video-av1_nvenc.yaml`    | Encode video with AV1 encoding using NVENC hardware            |
| `video-hevc_nvenc.yaml`   | Encode video using x265 encoding with NVENC hardware           |
| `video-vp9.yaml`          | Encode video with VP9 codec using CPU                          |

### Creating custom configuration files

The best way to create a custom configuration file to ensure it follows the correct schema is to:
1. Copy `config/default.yaml` to the new file destination
2. Remove the configuration options you don't wish to change
3. Edit the values of the remaining options and save the file

You can then apply your configuration using the `--config` command-line option of EstimPy's scripts using
```
python visualizer.py [actions] [options] --config path_to/config_file.yaml
```