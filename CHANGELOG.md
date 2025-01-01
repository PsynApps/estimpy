# Changelog

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