"""A python package for estim (estimpy)."""

import os
import subprocess
import typing
import sys

MIN_VERSION = (3, 11)

# Must use Python >=3.11
if sys.version_info < MIN_VERSION:
    raise RuntimeError(
        'Python version incompatibility\n'
        f'This package requires Python version >= {".".join(map(str, MIN_VERSION))}.\n'
        f'You are using Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}.\n'
        f'You will need to install a new Python environment with a compatible version to use this package.'
    )

import flatdict
import matplotlib
matplotlib.use('QtAgg')
import yaml

_config_path = os.path.dirname(__file__) + '/config'
_config_file_default = f'{_config_path}/default.yaml'

cfg = {}
listeners = {}

def add_event_listener(event: str, listener: typing.Callable):
    global listeners

    if event not in listeners:
        listeners[event] = []

    listeners[event].append(listener)


def trigger_event(event: str):
    global listeners

    if event in listeners:
        # Remove any non-callable listeners from the list
        listeners[event] = [listener for listener in listeners[event] if callable(listener)]
        # Call the listeners
        for listener in listeners[event]:
            listener()


def load_config(file: str):
    """
    Load a configuration file and merge it with the existing global config.
    :param file: The configuration file to load. If not found, will attempt to load a .yaml file from the estimpy package config directory.
    :return: None
    """
    _load_config(file)
    trigger_event('config.updated')


def load_configs(files: list):
    if files:
        for file in files:
            _load_config(file)
        trigger_event('config.updated')


def _check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise Exception('FFmpeg not found. Make sure FFmpeg is installed and available on your system path.')


def _check_ffprobe():
    try:
        subprocess.run(['ffprobe', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise Exception('FFprobe not found. Make sure FFprobe is installed and available on your system path.')


def _check_dependencies() -> None:
    _check_ffmpeg()
    _check_ffprobe()


def _load_config(file: str) -> None:
    global cfg

    if not os.path.exists(file):
        if not os.path.dirname(file):
            # If the file does not specify a directory, look in the estimpy package config directory
            file = f'{_config_path}/{file}'

            if not os.path.exists(file) and file.find('.yaml') == -1:
                # Try adding .yaml to the file
                file = f'{file}.yaml'

            if not os.path.exists(file):
                # We've tried everything, give up
                raise Exception(f'Error: Configuration file "{file}" does not exist.')

    with open(file, 'r') as file_handle:
        try:
            cfg.update(flatdict.FlatDict(yaml.safe_load(file_handle), delimiter='.'))
        except yaml.YAMLError as exc:
            raise Exception(f'Error loading default configuration file "{file}": {exc}')


_check_dependencies()

load_config('default')

from . import utils, metadata, audio, analysis, player, visualization, export

trigger_event('config.updated')
