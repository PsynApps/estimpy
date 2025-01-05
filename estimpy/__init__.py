"""A python package for Estim (estimpy)."""

import ast
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
import yaml

os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'  # Necessary to prevent forced DPI scaling on high DPI displays
import matplotlib
matplotlib.use('QtAgg')

_config_path = os.path.dirname(__file__) + '/config'
_config_file_default = f'{_config_path}/default.yaml'

# base_cfg stores the keys and values loaded from .yaml profiles, but does not store
# derived keys or updated values from the command line
base_cfg = {}

# cfg stores the current working configuration values for all keys
cfg = {}

# listeners stores event listeners
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


def update_config_values(values: dict):
    for key, value in values.items():
        if key not in cfg:
            raise Exception(f'Configuration key "{key}" is not valid.')

        key_type = type(cfg[key])

        try:
            if str(value).lower() in ['none', '~']:
                # Special case for None value which should skip type casting
                cfg[key] = None
            elif cfg[key] is None:
                # Current configuration value is None, so type can't be known (in current implementation)
                cfg[key] = value
            elif key_type == bool:
                # Normalize boolean values from strings and other types
                str_value = str(value).lower()

                if str_value in ['false', '0', '']:
                    cfg[key] = False
                elif str_value in ['true', '1']:
                    cfg[key] = True
                else:
                    raise ValueError()
            elif key_type == int:
                # Special case to allow float values for integer configuration options
                try:
                    # First try to cast value to integer
                    cfg[key] = key_type(value)
                except ValueError:
                    # If integer cast fails, try casting value to float
                    cfg[key] = float(value)
            elif key_type in [list, dict]:
                cfg[key] = ast.literal_eval(value)
            else:
                # Cast value to type of configuration option
                cfg[key] = key_type(value)
        except ValueError:
            # value is an incompatible type for configuration option
            raise Exception(f'Cannot cast {value} to {key_type}.')

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
            file_cfg = flatdict.FlatDict(yaml.safe_load(file_handle), delimiter='.')

            # Store base configuration (without derived values from config.updated handlers)
            # Needed to show which configuration options can be effectively updated from the command line
            base_cfg.update(file_cfg)

            # Update the main configuration
            cfg.update(file_cfg)
        except yaml.YAMLError as exc:
            raise Exception(f'Error loading default configuration file "{file}": {exc}')


_check_dependencies()

load_config('default')

from . import utils, metadata, audio, analysis, player, visualization, export

trigger_event('config.updated')
