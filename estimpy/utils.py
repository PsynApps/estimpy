"""Module for miscellaneous shared functionality"""

import argparse
import glob
import numpy as np
import os
import typing

import estimpy as es

_temp_files = []


def add_parser_arguments(parser: argparse.ArgumentParser, args: list = None) -> None:
    """Adds shared parser arguments to the argument parser

    :param argparse.ArgumentParser parser: A reference to the argument parser
    :param list args: A list of arguments to be added
    :return: None
    """
    if args is None:
        return

    if 'input_files' in args:
        parser.add_argument('-i', '--input-files', default=None, nargs='*', help='Input file(s). Supports wildcards.')

    if 'recursive' in args:
        parser.add_argument('-r', '--recursive', action='store_true', help='Load input files recursively')

    if 'output_path' in args:
        parser.add_argument('-o', '--output-path', default='./', help='Path to save output file(s). If not specified, uses the current path.')

    if 'config' in args:
        parser.add_argument('-c', '--config', default=None, nargs='*', help='Apply additional configuration file(s).')

    if 'dynamic_range' in args:
        parser.add_argument('-drange', '--dynamic-range', type=int,
                            help='Dynamic range to display on spectrogram (in decibels). Default is defined in default.yaml configuration file.')

    if 'frequency_min' in args:
        parser.add_argument('-fmin', '--frequency-min', type=int,
                            help='Minimum frequency to display on spectrogram. Default is defined in default.yaml configuration file.')

    if 'frequency_max' in args:
        parser.add_argument('-fmax', '--frequency-max', type=int,
                            help='Maximum frequency to display on spectrogram. If not defined, spectrogram will be autoscaled.')


def add_temp_file(temp_file):
    _temp_files.append(temp_file)


def delete_temp_files():
    for temp_file in _temp_files:
        if os.path.isfile(temp_file):
            os.remove(temp_file)

    _temp_files.clear()


def get_file_list(file_patterns: typing.Iterable, recursive: bool = None) -> list:
    """Takes an iterable of one or more file patterns and returns a list of all matching files.

    :param typing.Iterable file_patterns: An iterable that contains file patterns which can be parsed by glob.glob().
    :param bool recursive: Search file patterns recursively.
    :return list: A list of files which match the specified pattern(s) from input_files.
    """
    files = []

    recursive = recursive if recursive is not None else es.cfg['files.input.recursive']

    for input_file_pattern in file_patterns:
        if recursive:
            files_pattern = os.path.join(os.path.dirname(input_file_pattern), '**',
                                         os.path.basename(input_file_pattern))
            files += glob.glob(files_pattern, recursive=True)
        else:
            files += glob.glob(input_file_pattern)
    return files

def handle_parser_arguments(args: dict) -> None:
    """Handles shared parser arguments

    :param dict args: A dictionary with arguments as keys and values as values.
    :return: None
    """
    if args is None:
        return

    argkeys = args.keys()

    # Important to load config files
    argkey = 'config'
    if argkey in argkeys and args[argkey]:
        es.load_configs(args[argkey])

    argkey = 'recursive'
    if argkey in argkeys and args[argkey] is not None:
        es.cfg['files.input.recursive'] = args[argkey]

    argkey = 'output_path'
    if argkey in argkeys and args[argkey] is not None:
        es.cfg['files.output.path'] = args[argkey]

    argkey = 'dynamic_range'
    if argkey in argkeys and args[argkey] is not None:
        es.cfg['visualization.style.spectrogram.dynamic-range'] = args[argkey]

    argkey = 'frequency_min'
    if argkey in argkeys and args[argkey] is not None:
        es.cfg['analysis.spectrogram.frequency-min'] = args[argkey]

    argkey = 'frequency_max'
    if argkey in argkeys and args[argkey] is not None:
        es.cfg['analysis.spectrogram.frequency-max'] = args[argkey]


def log10_quiet(x: int | float | np.ndarray | typing.Iterable, *args: typing.Any, **kwargs: typing.Any) -> np.ndarray:
    """Calls numpy.log10 while suppressing divide-by-zero errors, which is useful to prevent unnecessary console
    output when generating a spectrogram.

    :param int | float | np.ndarray | typing.Iterable x:
    :param typing.Any args:
    :param typing.Any kwargs:
    """
    old_settings = np.seterr(divide='ignore')
    y = np.log10(x, *args, **kwargs)
    np.seterr(**old_settings)
    return y


def seconds_to_string(seconds: int | float = 0):
    """Converts a number of seconds to a formatted string

    :param int seconds: The number of seconds
    :return string: A string representation of the number of seconds.
    """
    # Calculate total seconds, then days, hours, minutes, and seconds
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Format based on duration
    if days > 0:
        return f'{int(days)}:{int(hours):02}:{int(minutes):02}:{int(seconds):02}'
    elif hours > 0:
        return f'{int(hours)}:{int(minutes):02}:{int(seconds):02}'
    else:
        return f'{int(minutes)}:{int(seconds):02}'

