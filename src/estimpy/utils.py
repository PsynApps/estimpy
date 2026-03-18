"""Module for miscellaneous shared functionality"""

import glob
import itertools
import numpy as np
import os
import random
import string
import sys
import tempfile
import threading
import time
import typing

import estimpy as es

_temp_files = []


class Spinner:
    """Terminal spinner that shows a rotating character alongside a message.

    Can be used as a context manager to guarantee cleanup on exceptions::

        with Spinner('Loading... ') as s:
            do_work()
    """

    _CLEAR_LINE = '\033[2K\r'

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    def start(self):
        """Start the spinner in a separate thread."""
        def run_spinner():
            while self.running.is_set():
                sys.stdout.write(f"{self._CLEAR_LINE}{self.message}{next(self.spinner)}")
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
            sys.stdout.write(f"{self._CLEAR_LINE}{self.message}{stop_message}\n")
            sys.stdout.flush()


def add_temp_file(temp_file):
    if temp_file is not None:
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

    # Sort the files for a predictable order
    files.sort()

    return files


def prompt_file_dialog(title: str = 'Select file(s)') -> tuple:
    """Show a Qt file dialog to select one or more files.

    :param str title: The title of the file dialog window.
    :return tuple: A tuple of selected file paths, or an empty tuple if cancelled.
    """
    from PyQt6.QtWidgets import QApplication, QFileDialog
    app = QApplication.instance() or QApplication([])
    files, _ = QFileDialog.getOpenFileNames(None, title, '.')
    return tuple(files)


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
    """Return a path in the system temp directory, optionally for a named file.

    When a file name is provided, a short random suffix is inserted before the
    extension to avoid collisions between concurrent processes.
    """
    temp_dir = tempfile.gettempdir()
    if temp_file_name is None:
        return temp_dir
    base, ext = os.path.splitext(temp_file_name)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return os.path.join(temp_dir, f'{base}_{suffix}{ext}')


def log10_quiet(x: int | float | np.ndarray | typing.Iterable, *args: typing.Any, **kwargs: typing.Any) -> np.ndarray:
    """Calls numpy.log10 while suppressing divide-by-zero errors, which is useful to prevent unnecessary console
    output when generating a spectrogram.

    :param int | float | np.ndarray | typing.Iterable x:
    :param typing.Any args:
    :param typing.Any kwargs:
    """
    with np.errstate(divide='ignore'):
        return np.log10(x, *args, **kwargs)


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
