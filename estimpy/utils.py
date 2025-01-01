"""Module for miscellaneous shared functionality"""

import argparse
import glob
import itertools
import numpy as np
import os
import sys
import tempfile
import threading
import time
import typing

import estimpy as es

_temp_files = []


class Spinner:
    def __init__(self, message: str = '', autostart: bool = True, rate: float = 0.1):
        """
        Initialize the spinner.
        :param message: Message to display before the spinner.
        :param rate: Time delay between spinner updates.
        """
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])
        self.message = message
        self.rate = rate

        self.running = threading.Event()
        self.thread = None

        if autostart:
            self.start()

    def start(self):
        """Start the spinner in a separate thread."""
        def run_spinner():
            while self.running.is_set():
                sys.stdout.write(f"\r{self.message}{next(self.spinner)}")  # Overwrite the line
                sys.stdout.flush()
                time.sleep(self.rate)

        if not self.thread or not self.thread.is_alive():
            self.running.set()
            self.thread = threading.Thread(target=run_spinner, daemon=True)
            self.thread.start()

    def stop(self, stop_message: str = ''):
        """Stop the spinner."""
        if self.running.is_set():
            self.running.clear()
            self.thread.join()
            sys.stdout.write(f"\r{self.message}{stop_message} \n")  # Clear spinner character
            sys.stdout.flush()


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
        parser.add_argument('-c', '--config', default=None, nargs='*', help='Apply additional configuration profile(s).')

    if 'config_option' in args:
        parser.add_argument('-co', '--config-option', default=None, nargs='*', help='Overwrite specific configuration option(s). Applies after all configuration files have been processed. Configuration options follow the structure from default.yaml using dots in place of indents with values after a space.')

    if 'config_option_list' in args:
        parser.add_argument('-col', '--config-option-list', action='store_true', help='List all valid config options and exit')

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
    if temp_file is not None:
        _temp_files.append(temp_file)


def delete_temp_files():
    for temp_file in _temp_files:
        if os.path.isfile(temp_file):
            os.remove(temp_file)

    _temp_files.clear()


def get_default_parser_arguments() -> list:
    return ['input_files', 'recursive', 'config', 'config_option', 'config_option_list',
            'dynamic_range', 'frequency_min', 'frequency_max']


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


def get_output_file(output_path: str, input_file_name: str, file_format: str) -> str:
    # Convert path to absolute path
    output_path = os.path.abspath(output_path)
    output_file_base_name = None

    if os.path.isdir(output_path):
        output_dir = output_path
    else:
        output_dir = os.path.dirname(output_path)

        if not output_dir:
            output_dir = '.'

        output_file_base_name, _ = os.path.splitext(os.path.basename(output_path))

    if not output_file_base_name:
        output_file_base_name, _ = os.path.splitext(os.path.basename(input_file_name))

    return f'{output_dir}{os.sep}{output_file_base_name}.{file_format}'


def get_temp_file_path(temp_file_name: str = None) -> str:
    temp_file_path = tempfile.gettempdir()
    if temp_file_name is not None:
        temp_file_path += f'{os.sep}{temp_file_name}'
    return temp_file_path


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

    # Allows overriding any configuration option(s) by specifying a key value pair(s)
    # e.g. -config_option
    argkey = 'config_option'
    if argkey in argkeys and args[argkey] is not None:
        config_options = args[argkey].copy()

        config_option_values = {}
        while len(config_options) > 0:
            # Configuration options must have a key and a value pair
            if len(config_options) < 2:
                raise Exception(f'No value specified for configuration option "{config_options[0]}".')

            key, value, *config_options = config_options
            config_option_values[key] = value

        es.update_config_values(config_option_values)

    # List all config options
    argkey = 'config_option_list'
    if argkey in argkeys and args[argkey]:
        # Calculate the maximum width for keys and values
        key_width = max(len(key) for key in es.base_cfg)

        header_text = f'{"Configuration option".ljust(key_width)}  {"Value"}'
        print(header_text)
        print('=' * len(header_text))

        # Iterate and print keys and values left-justified
        # Note we are only showing keys in base_cfg since derived keys
        # from config.updated event handlers will be overwritten from base values.
        for key in sorted(es.base_cfg):
            print(f"{key.ljust(key_width)}: {str(es.cfg[key])}")

        sys.exit()
    # Configuration option shortcuts
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


def validate_output_file(output_file: str, overwrite: bool = None) -> bool:
    """Determines whether an output file target can or should be written.
    :param output_file:
    :param overwrite:
    :return: bool
    """
    # Conceptually, this function is looking for reasons to say no (return False)
    # If none are found, the end of the function will return True
    overwrite = es.cfg['files.output.overwrite-default'] if overwrite is None else overwrite

    # Check if the file exists
    # If overwrite-default is set to True, skip any prompting and allow validation to continue
    if os.path.exists(output_file) and not overwrite:
        responses_yes = ['y', 'yes']
        responses_no = ['n', 'no']
        responses_all = ['a', 'all']
        responses_none = ['none']

        # If overwrite-prompt is False, reject validation without prompting user
        # (We already checked that overwrite-default is False)
        if not es.cfg['files.output.overwrite-prompt']:
            return False

        while True:
            response = input(
                f"'{output_file}' already exists. Overwrite it? (y)es/(n)o/(a)ll/none): "
            ).strip().lower()
            if response in responses_yes:
                # Allow validation to continue
                break
            elif response in responses_no:
                # Do not overwrite, reject validation
                return False
            elif response in responses_all:
                # Change overwrite-default configuration to True and allow validation to continue
                es.cfg['files.output.overwrite-default'] = True
                break
            elif response in responses_none:
                # Change overwrite-prompt configuration to False and reject validation
                es.cfg['files.output.overwrite-prompt'] = False
                return False
            else:
                print('Please enter "y" (yes), "n" (no), "a" (yes to all), or "none" (no to all).')

    # Make sure the output file directory exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        raise Exception(f'Cannot write to "{output_file}": Directory does not exist.')

    # Make sure the user has permissions to write to the output file
    if (os.path.exists(output_file) and not os.access(output_file, os.W_OK)) or \
            (not os.path.exists(output_file) and not os.access(output_dir, os.W_OK)):
        raise Exception(f'Cannot write to "{output_file}": Permission denied.')

    # No validation checks failed, so return True
    return True
