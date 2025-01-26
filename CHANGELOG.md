# Changelog

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