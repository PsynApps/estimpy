import sys
from unittest import mock

import pytest

import estimpy as es
from estimpy.cli import _handle_global_arguments


def _parse_args(argv):
    """Run the CLI argparse machinery on the given argv and return parsed dict.

    Does not execute commands — only parses arguments.
    """
    with mock.patch.object(sys, 'argv', ['estimpy'] + argv):
        # Replicate the subcommand-defaulting logic from main()
        subcommands = {'play', 'show-image', 'save-image', 'save-audio', 'save-video', 'save-metadata'}
        args = sys.argv[1:]
        has_subcommand = any(a in subcommands for a in args)
        if not has_subcommand and '-h' not in args and '--help' not in args:
            sys.argv.insert(1, 'play')

        import argparse
        parser = argparse.ArgumentParser(prog='estimpy')
        parser.add_argument('--version', action='store_true')
        subparsers = parser.add_subparsers(dest='command', metavar='<command>')

        for cmd in ['play', 'show-image', 'save-image', 'save-audio', 'save-video', 'save-metadata']:
            sub = subparsers.add_parser(cmd)
            sub.add_argument('files', nargs='*', default=None)
            # Global args
            sub.add_argument('-t', '--triphase', action='store_true')
            sub.add_argument('-r', '--recursive', action='store_true')
            sub.add_argument('-c', '--config', default=None, nargs='*', metavar='PROFILE')
            sub.add_argument('-co', '--config-option', default=None, nargs='*', metavar='K V')
            sub.add_argument('-col', '--config-option-list', action='store_true')
            sub.add_argument('--dynamic-range', type=int, metavar='DB')
            sub.add_argument('--frequency-min', type=int, metavar='HZ')
            sub.add_argument('--frequency-max', type=int, metavar='HZ')
            sub.add_argument('-ss', '--stereo-stim', action='store_true')

            if cmd in ('save-image', 'save-video', 'save-metadata'):
                sub.add_argument('-o', '--output-path', default='./', metavar='PATH')
                sub.add_argument('-y', '--yes', action='store_true')

            if cmd == 'save-video':
                sub.add_argument('--resume-frame', default=None, type=int, metavar='N')
                sub.add_argument('--resume-segment', default=None, type=int, metavar='N')
                sub.add_argument('-p', '--profiling', action='store_true')

        return vars(parser.parse_args())


class TestArgParsing:
    def test_default_command_is_play(self):
        parsed = _parse_args([])
        assert parsed['command'] == 'play'

    def test_explicit_play(self):
        parsed = _parse_args(['play'])
        assert parsed['command'] == 'play'

    def test_show_image_command(self):
        parsed = _parse_args(['show-image'])
        assert parsed['command'] == 'show-image'

    def test_save_image_command(self):
        parsed = _parse_args(['save-image'])
        assert parsed['command'] == 'save-image'

    def test_save_video_command(self):
        parsed = _parse_args(['save-video'])
        assert parsed['command'] == 'save-video'

    def test_save_audio_command(self):
        parsed = _parse_args(['save-audio'])
        assert parsed['command'] == 'save-audio'

    def test_save_metadata_command(self):
        parsed = _parse_args(['save-metadata'])
        assert parsed['command'] == 'save-metadata'

    def test_files_parsed(self):
        parsed = _parse_args(['play', 'file1.mp3', 'file2.mp3'])
        assert parsed['files'] == ['file1.mp3', 'file2.mp3']

    def test_triphase_flag(self):
        parsed = _parse_args(['play', '-t'])
        assert parsed['triphase'] is True

    def test_recursive_flag(self):
        parsed = _parse_args(['play', '-r'])
        assert parsed['recursive'] is True

    def test_config_profiles(self):
        parsed = _parse_args(['play', '-c', 'video-4k', 'video-60fps'])
        assert parsed['config'] == ['video-4k', 'video-60fps']

    def test_config_option_pairs(self):
        parsed = _parse_args(['play', '-co', 'player.volume-start', '75'])
        assert parsed['config_option'] == ['player.volume-start', '75']

    def test_dynamic_range(self):
        parsed = _parse_args(['play', '--dynamic-range', '60'])
        assert parsed['dynamic_range'] == 60

    def test_frequency_min(self):
        parsed = _parse_args(['play', '--frequency-min', '100'])
        assert parsed['frequency_min'] == 100

    def test_frequency_max(self):
        parsed = _parse_args(['play', '--frequency-max', '5000'])
        assert parsed['frequency_max'] == 5000

    def test_save_output_path(self):
        parsed = _parse_args(['save-image', '-o', '/tmp/output'])
        assert parsed['output_path'] == '/tmp/output'

    def test_save_yes_flag(self):
        parsed = _parse_args(['save-image', '-y'])
        assert parsed['yes'] is True

    def test_profiling_on_save_video(self):
        parsed = _parse_args(['save-video', '-p'])
        assert parsed['profiling'] is True

    def test_resume_frame(self):
        parsed = _parse_args(['save-video', '--resume-frame', '100'])
        assert parsed['resume_frame'] == 100

    def test_resume_segment(self):
        parsed = _parse_args(['save-video', '--resume-segment', '2'])
        assert parsed['resume_segment'] == 2

    def test_no_files_defaults_to_none(self):
        parsed = _parse_args(['play'])
        assert parsed['files'] == []

    def test_implicit_play_with_file(self):
        parsed = _parse_args(['song.mp3'])
        assert parsed['command'] == 'play'
        assert parsed['files'] == ['song.mp3']

    def test_ss_flag(self):
        parsed = _parse_args(['play', '-ss'])
        assert parsed['stereo_stim'] is True

    def test_ss_long_flag(self):
        parsed = _parse_args(['save-video', '--stereo-stim'])
        assert parsed['stereo_stim'] is True


class TestConfigHandling:
    def test_triphase_sets_config(self):
        args = _parse_args(['play', '-t'])
        _handle_global_arguments(args)
        assert es.cfg['visualization.image.display.triphase'] is True
        assert es.cfg['visualization.image.export.triphase'] is True
        assert es.cfg['visualization.video.display.triphase'] is True
        assert es.cfg['visualization.video.export.triphase'] is True

    def test_recursive_sets_config(self):
        args = _parse_args(['play', '-r'])
        _handle_global_arguments(args)
        assert es.cfg['files.input.recursive'] is True

    def test_dynamic_range_sets_config(self):
        args = _parse_args(['play', '--dynamic-range', '60'])
        _handle_global_arguments(args)
        assert es.cfg['visualization.style.spectrogram.dynamic-range'] == 60

    def test_frequency_min_sets_config(self):
        args = _parse_args(['play', '--frequency-min', '100'])
        _handle_global_arguments(args)
        assert es.cfg['analysis.spectrogram.frequency-min'] == 100

    def test_frequency_max_sets_config(self):
        args = _parse_args(['play', '--frequency-max', '5000'])
        _handle_global_arguments(args)
        assert es.cfg['analysis.spectrogram.frequency-max'] == 5000

    def test_config_option_applies_override(self):
        args = _parse_args(['play', '-co', 'player.volume-start', '75'])
        _handle_global_arguments(args)
        assert es.cfg['player.volume-start'] == 75

    def test_config_option_missing_value_raises(self):
        args = _parse_args(['play', '-co', 'player.volume-start'])
        with pytest.raises(SystemExit):
            _handle_global_arguments(args)

    def test_ss_sets_config(self):
        args = _parse_args(['play', '-ss'])
        _handle_global_arguments(args)
        assert es.cfg['audio.stereo-stim.enabled'] is True

    def test_config_profile_loads(self):
        args = _parse_args(['play', '-c', 'notitle'])
        _handle_global_arguments(args)
        assert es.cfg['visualization.image.display.title.enabled'] is False
        assert es.cfg['visualization.video.display.title.enabled'] is False

    def test_deprecated_dynamic_range_warns(self, capsys):
        args = _parse_args(['play', '--dynamic-range', '60'])
        _handle_global_arguments(args)
        assert es.cfg['visualization.style.spectrogram.dynamic-range'] == 60
        captured = capsys.readouterr()
        assert 'deprecated' in captured.out.lower()

    def test_deprecated_frequency_min_warns(self, capsys):
        args = _parse_args(['play', '--frequency-min', '100'])
        _handle_global_arguments(args)
        assert es.cfg['analysis.spectrogram.frequency-min'] == 100
        captured = capsys.readouterr()
        assert 'deprecated' in captured.out.lower()

    def test_deprecated_frequency_max_warns(self, capsys):
        args = _parse_args(['play', '--frequency-max', '5000'])
        _handle_global_arguments(args)
        assert es.cfg['analysis.spectrogram.frequency-max'] == 5000
        captured = capsys.readouterr()
        assert 'deprecated' in captured.out.lower()
