"""
EstimPy CLI

Unified command-line interface for EstimPy audio visualization and playback.

Usage:
    estimpy [files...]                  Launch the interactive player (default)
    estimpy play [files...]             Launch the interactive player
    estimpy show-image [files...]       Show a static image visualization
    estimpy save-image [files...]       Save image visualization to file(s)
    estimpy save-video [files...]       Save animated visualization to video file(s)
    estimpy save-metadata [files...]    Write album art to audio file metadata
    estimpy benchmark [file]            Benchmark video encoding profiles
"""

import argparse
import copy
import glob
import logging
import os
import sys
import time

import estimpy as es


def main():
    logging.getLogger().setLevel(logging.ERROR)

    # Handle --version before argparse (works with or without a subcommand)
    if '--version' in sys.argv[1:]:
        import importlib.metadata
        print(importlib.metadata.version('estimpy'))
        sys.exit()

    # Check if any argument is a known subcommand. If not, default to 'play'.
    subcommands = {'play', 'show-image', 'save-image', 'save-video', 'save-metadata', 'benchmark'}
    args = sys.argv[1:]
    has_subcommand = any(a in subcommands for a in args)
    if not has_subcommand and '-h' not in args and '--help' not in args:
        sys.argv.insert(1, 'play')

    parser = argparse.ArgumentParser(
        prog='estimpy',
        description='EstimPy - Audio visualization and playback for estim audio',
        epilog="Run 'estimpy <command> --help' for more information on a command.\n"
               'If no command is given, the player is launched.',
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--version', action='store_true', help='Display version information and exit.')

    subparsers = parser.add_subparsers(dest='command', metavar='<command>')

    # play
    parser_play = subparsers.add_parser('play',
        help='Launch the interactive player',
        description='Launch the interactive player for estim audio files with real-time visualization and independent channel volume control.')
    parser_play.add_argument('files', nargs='*', default=None, help='Input audio file(s). Supports wildcards.')
    _add_global_arguments(parser_play)

    # show-image
    parser_show = subparsers.add_parser('show-image',
        help='Show a static image visualization',
        description='Display an interactive window with the image visualization of the input file(s).')
    parser_show.add_argument('files', nargs='*', default=None, help='Input audio file(s). Supports wildcards.')
    _add_global_arguments(parser_show)

    # save-image
    parser_save_image = subparsers.add_parser('save-image',
        help='Save image visualization to file(s)',
        description='Save an image file with visualization of the input file(s). Output files use the same base name as the input file.')
    parser_save_image.add_argument('files', nargs='*', default=None, help='Input audio file(s). Supports wildcards.')
    _add_global_arguments(parser_save_image)
    _add_save_arguments(parser_save_image)

    # save-video
    parser_save_video = subparsers.add_parser('save-video',
        help='Save animated visualization to video file(s)',
        description='Save a video file with an animated visualization of the input file(s). Output files use the audio track from the input file.')
    parser_save_video.add_argument('files', nargs='*', default=None, help='Input audio file(s). Supports wildcards.')
    _add_global_arguments(parser_save_video)
    _add_save_arguments(parser_save_video)
    parser_save_video.add_argument('--resume-frame', default=None, type=int, metavar='N',
        help='Frame on which to resume video encoding. Useful if encoding crashes during a large file.')
    parser_save_video.add_argument('--resume-segment', default=None, type=int, metavar='N',
        help='Segment on which to resume video encoding. Will not work correctly if segment-length configuration value is changed between runs.')
    parser_save_video.add_argument('-p', '--profiling', action='store_true',
        help='Enable profiling output for video export. Prints per-frame timing breakdown to stdout.')

    # save-metadata
    parser_save_metadata = subparsers.add_parser('save-metadata',
        help='Write album art to audio file metadata',
        description='Modify the input file(s) to add or replace the album art metadata with the image visualization. Only supported for mp3, mp4, and m4a files.')
    parser_save_metadata.add_argument('files', nargs='*', default=None, help='Input audio file(s). Supports wildcards.')
    _add_global_arguments(parser_save_metadata)
    _add_save_arguments(parser_save_metadata)

    # benchmark
    parser_benchmark = subparsers.add_parser('benchmark',
        help='Benchmark video encoding profiles',
        description='Encode a test file using each video profile and report encoding time, speed, and file size. '
                    'If no input file is specified, uses the bundled benchmark audio file.')
    parser_benchmark.add_argument('file', nargs='?', default=None, help='Input audio file. If not specified, uses the bundled benchmark file.')

    parsed = vars(parser.parse_args())

    # Handle global arguments (version, config, config options, etc.)
    if parsed['command'] != 'benchmark':
        _handle_global_arguments(parsed)

    command = parsed['command']

    if command == 'play':
        _run_play(parsed)
    elif command == 'show-image':
        _run_show_image(parsed)
    elif command == 'save-image':
        _run_save_image(parsed)
    elif command == 'save-video':
        _run_save_video(parsed)
    elif command == 'save-metadata':
        _run_save_metadata(parsed)
    elif command == 'benchmark':
        _run_benchmark(parsed)


def _add_global_arguments(parser):
    """Add global arguments shared across all subcommands."""
    parser.add_argument('-t', '--triphase', action='store_true',
        help='Visualize stereo audio as 3 channels: A, B, and the triphase signal -(A+B) at the common electrode.')
    parser.add_argument('-r', '--recursive', action='store_true', help='Load input files recursively.')
    parser.add_argument('-c', '--config', default=None, nargs='*', metavar='PROFILE',
        help='Apply additional configuration profile(s).')
    parser.add_argument('-co', '--config-option', default=None, nargs='*', metavar='K V',
        help='Override specific configuration option(s). Options follow the structure from default.yaml using dots in place of indents with values after a space.')
    parser.add_argument('-col', '--config-option-list', action='store_true',
        help='List all valid config options and exit.')
    parser.add_argument('--dynamic-range', type=int, metavar='DB',
        help='Dynamic range to display on spectrogram (in decibels).')
    parser.add_argument('--frequency-min', type=int, metavar='HZ',
        help='Minimum frequency to display on spectrogram.')
    parser.add_argument('--frequency-max', type=int, metavar='HZ',
        help='Maximum frequency to display on spectrogram. If not defined, spectrogram will be autoscaled.')


def _add_save_arguments(parser):
    """Add arguments shared across save subcommands."""
    parser.add_argument('-o', '--output-path', default='./', metavar='PATH',
        help='Path to save output file(s). If not specified, uses the current directory.')
    parser.add_argument('-y', '--yes', action='store_true',
        help='Answers yes to all interactive prompts (overwrites existing output files by default).')


def _handle_global_arguments(args):
    """Process global arguments that apply before subcommand execution."""
    # Load config profiles
    if args.get('config'):
        es.load_configs(args['config'])

    # Override specific config options
    config_option = args.get('config_option')
    if config_option is not None:
        config_options = config_option.copy()
        config_option_values = {}
        while len(config_options) > 0:
            if len(config_options) < 2:
                raise SystemExit(f'Error: No value specified for configuration option "{config_options[0]}".')
            key, value, *config_options = config_options
            config_option_values[key] = value
        es.update_config_values(config_option_values)

    # List config options
    if args.get('config_option_list'):
        key_width = max(len(key) for key in es.base_cfg)
        header_text = f'{"Configuration option".ljust(key_width)}  {"Value"}'
        print(header_text)
        print('=' * len(header_text))
        for key in sorted(es.base_cfg):
            print(f"{key.ljust(key_width)}: {str(es.cfg[key])}")
        sys.exit()

    # Apply shortcut config overrides
    if args.get('recursive') is not None:
        es.cfg['files.input.recursive'] = args['recursive']

    if args.get('output_path') is not None:
        es.cfg['files.output.path'] = args['output_path']

    if args.get('dynamic_range') is not None:
        es.cfg['visualization.style.spectrogram.dynamic-range'] = args['dynamic_range']

    if args.get('frequency_min') is not None:
        es.cfg['analysis.spectrogram.frequency-min'] = args['frequency_min']

    if args.get('frequency_max') is not None:
        es.cfg['analysis.spectrogram.frequency-max'] = args['frequency_max']

    # Apply triphase
    if args.get('triphase'):
        es.cfg['visualization.triphase'] = True


def _get_files(args):
    """Get the list of input files from arguments, prompting if none given."""
    input_files = args.get('files')

    if not input_files:
        input_files = es.utils.prompt_file_dialog(title='Select file(s)')

    if not input_files:
        sys.exit()

    return es.utils.get_file_list(file_patterns=input_files)


def _load_audio(file, triphase=False):
    """Load an audio file and optionally apply triphase transformation."""
    with es.utils.Spinner(f'Loading file {file}... '):
        es_audio = es.audio.Audio(file=file)

    if triphase and es_audio.channels == 2:
        es_audio = es_audio.with_triphase()
    elif triphase:
        print(f'Warning: Triphase requires stereo audio, ignoring -t for {file}')

    return es_audio


def _run_play(args):
    """Launch the interactive player."""
    input_files = args.get('files')

    if not input_files:
        input_files = es.utils.prompt_file_dialog(title='Select file(s)')

    audio_files = es.utils.get_file_list(file_patterns=input_files) if input_files else []

    video_player = es.player.Player(audio_files=audio_files)
    video_player.show()


def _run_show_image(args):
    """Show static image visualization for each input file."""
    files = _get_files(args)
    triphase = args.get('triphase', False)

    for file in files:
        try:
            es_audio = _load_audio(file, triphase=triphase)
            es.visualization.show_image(es_audio=es_audio)
        except Exception as e:
            print(e)


def _run_save_image(args):
    """Save image visualization for each input file."""
    files = _get_files(args)
    triphase = args.get('triphase', False)

    if args.get('yes'):
        es.cfg['files.output.overwrite-default'] = True

    for file in files:
        try:
            es_audio = _load_audio(file, triphase=triphase)
            es.export.write_image(es_audio=es_audio)
        except Exception as e:
            print(e)


def _run_save_video(args):
    """Save video visualization for each input file."""
    files = _get_files(args)
    triphase = args.get('triphase', False)
    resume_frame = args.get('resume_frame')
    resume_segment = args.get('resume_segment')
    profiling = args.get('profiling', False)

    if args.get('yes'):
        es.cfg['files.output.overwrite-default'] = True

    for file in files:
        try:
            es_audio = _load_audio(file, triphase=triphase)
            es.export.write_video(es_audio=es_audio,
                frame_start=resume_frame, segment_start=resume_segment,
                profiling=profiling)
        except Exception as e:
            print(e)


def _run_save_metadata(args):
    """Write album art metadata for each input file."""
    files = _get_files(args)
    triphase = args.get('triphase', False)

    if args.get('yes'):
        es.cfg['files.output.overwrite-default'] = True

    for file in files:
        try:
            es_audio = _load_audio(file, triphase=triphase)
            es.metadata.write_metadata(es_audio=es_audio)
        except Exception as e:
            print(e)


def _run_benchmark(args):
    """Benchmark video encoding across all video profiles."""
    # Determine input file
    input_file = args.get('file')
    if not input_file:
        input_file = os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'input', 'benchmark.mp3')
        input_file = os.path.normpath(input_file)

    if not os.path.exists(input_file):
        if args.get('file'):
            print(f'Error: File not found: {input_file}')
        else:
            print('Error: Bundled benchmark file not found. Please specify an input file:')
            print('  estimpy benchmark <audio-file>')
        sys.exit(1)

    print(f'Benchmark input: {input_file}')

    # Load audio once
    es_audio = _load_audio(input_file)

    # Discover video profiles dynamically from the config directory
    config_path = os.path.join(os.path.dirname(__file__), 'config')
    profile_files = sorted(glob.glob(os.path.join(config_path, 'video-*.yaml')))
    profile_names = [os.path.splitext(os.path.basename(f))[0] for f in profile_files]

    # Build run list: default first, then each video profile
    runs = [('default', None)] + [(name.removeprefix('video-'), name) for name in profile_names]

    print(f'Found {len(runs)} profiles to benchmark: {", ".join(name for name, _ in runs)}')
    print()

    # Snapshot the default config state to restore between runs
    default_cfg = copy.deepcopy(dict(es.cfg))
    default_base_cfg = copy.deepcopy(dict(es.base_cfg))

    results = []
    output_dir = es.utils.get_temp_file_path()
    os.makedirs(output_dir, exist_ok=True)

    for i, (display_name, profile_name) in enumerate(runs):
        # Restore config to default state
        es.cfg.clear()
        es.cfg.update(copy.deepcopy(default_cfg))
        es.base_cfg.clear()
        es.base_cfg.update(copy.deepcopy(default_base_cfg))

        # Load the profile on top of defaults
        if profile_name is not None:
            try:
                es.load_config(profile_name)
            except Exception as e:
                print(f'[{i + 1}/{len(runs)}] {display_name}: Failed to load profile — {e}')
                results.append({'name': display_name, 'error': str(e)})
                print()
                continue

        # Disable preview to focus on encode timing
        es.cfg['visualization.video.export.preview.enabled'] = False
        es.cfg['files.output.overwrite-default'] = True
        es.trigger_event('config.updated')

        # Read effective settings for this profile
        codec = es.cfg['visualization.video.export.codec']
        resolution = f'{es.cfg["visualization.video.export.width"]}x{es.cfg["visualization.video.export.height"]}'
        fps = es.cfg['visualization.video.export.fps']

        print(f'[{i + 1}/{len(runs)}] {display_name} ({codec}, {resolution}, {fps} fps)')
        print('─' * 60)

        try:
            start_time = time.time()
            video_file = es.export.write_video(
                es_audio=es_audio,
                output_path=output_dir,
                overwrite=True)
            elapsed = time.time() - start_time

            if video_file and os.path.exists(video_file):
                file_size = os.path.getsize(video_file)
                total_frames = int(es_audio.length * fps)
                encoding_fps = total_frames / elapsed if elapsed > 0 else 0

                results.append({
                    'name': display_name,
                    'codec': codec,
                    'resolution': resolution,
                    'fps': fps,
                    'time': elapsed,
                    'encoding_fps': encoding_fps,
                    'file_size': file_size,
                })

                # Clean up output file
                os.remove(video_file)
            else:
                results.append({'name': display_name, 'error': 'No output file produced'})
        except Exception as e:
            results.append({
                'name': display_name,
                'codec': codec,
                'resolution': resolution,
                'fps': fps,
                'error': str(e),
            })
            # Clean up any temp files left behind
            es.utils.delete_temp_files()
            print(f'FAILED: {e}')

        print()

    # Clean up temp directory
    try:
        os.rmdir(output_dir)
    except OSError:
        pass

    # Print summary table
    _print_benchmark_summary(results)


def _format_file_size(size_bytes):
    """Format a file size in bytes to a human-readable string."""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.2f} GB'


def _print_benchmark_summary(results):
    """Print a formatted summary table of benchmark results."""
    if not results:
        print('No benchmark results to display.')
        return

    # Column definitions: (header, key, width, formatter)
    columns = [
        ('Profile', 'name', None, str),
        ('Codec', 'codec', None, str),
        ('Resolution', 'resolution', None, str),
        ('FPS', 'fps', 5, lambda v: str(int(v))),
        ('Time', 'time', 10, lambda v: es.utils.seconds_to_string(v)),
        ('Enc. FPS', 'encoding_fps', 10, lambda v: f'{v:.1f}'),
        ('File Size', 'file_size', 10, _format_file_size),
    ]

    # Compute column widths from data (use max of header and longest value)
    col_widths = []
    for header, key, min_width, formatter in columns:
        width = len(header)
        for r in results:
            if 'error' not in r and key in r:
                width = max(width, len(formatter(r[key])))
            elif key == 'name':
                width = max(width, len(r['name']))
        if min_width:
            width = max(width, min_width)
        col_widths.append(width)

    # Print header
    header_parts = [columns[i][0].ljust(col_widths[i]) for i in range(len(columns))]
    header_line = '  '.join(header_parts)
    print('Benchmark Results')
    print('=' * len(header_line))
    print(header_line)
    print('─' * len(header_line))

    # Print rows
    for r in results:
        if 'error' in r:
            name = r['name'].ljust(col_widths[0])
            # Show codec/resolution/fps if available, then error
            error_parts = [name]
            for i, (_, key, _, formatter) in enumerate(columns[1:], 1):
                if key in r:
                    error_parts.append(formatter(r[key]).ljust(col_widths[i]))
                else:
                    break
            error_msg = f'FAILED ({r["error"]})'
            # Pad remaining columns and append error
            filled = len(error_parts)
            if filled < len(columns):
                remaining_width = sum(col_widths[filled:]) + 2 * (len(columns) - filled)
                error_parts.append(error_msg[:remaining_width].ljust(remaining_width))
            print('  '.join(error_parts))
        else:
            parts = []
            for i, (_, key, _, formatter) in enumerate(columns):
                parts.append(formatter(r[key]).ljust(col_widths[i]))
            print('  '.join(parts))

    print('─' * len(header_line))

    # Print fastest/smallest summary for successful runs
    successful = [r for r in results if 'error' not in r]
    if successful:
        fastest = min(successful, key=lambda r: r['time'])
        smallest = min(successful, key=lambda r: r['file_size'])
        print(f'Fastest:  {fastest["name"]} ({es.utils.seconds_to_string(fastest["time"])}, {fastest["encoding_fps"]:.1f} enc. fps)')
        print(f'Smallest: {smallest["name"]} ({_format_file_size(smallest["file_size"])})')

    print()


if __name__ == '__main__':
    main()
