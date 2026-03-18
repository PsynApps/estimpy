"""A python package for Estim (estimpy)."""

import ast
import importlib.metadata
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

import yaml

os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'  # Necessary to prevent forced DPI scaling on high DPI displays
import matplotlib
matplotlib.use('QtAgg')

_config_path = os.path.dirname(__file__) + '/config'
_user_config_path = os.path.expanduser('~/.estimpy')

# base_cfg stores the keys and values loaded from .yaml profiles, but does not store
# derived keys or updated values from the command line
base_cfg = {}

# cfg stores the current working configuration values for all keys
cfg = {}

# listeners stores event listeners
listeners = {}

def add_event_listener(event: str, listener: typing.Callable):
    if event not in listeners:
        listeners[event] = []

    listeners[event].append(listener)


def trigger_event(event: str):
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


def check_dependencies() -> None:
    """Verify that FFmpeg and FFprobe are available on the system PATH.

    Called lazily before operations that need them (export, video encoding)
    rather than at import time, so that non-export functionality (analysis,
    visualization, player with pre-encoded audio) works without FFmpeg.
    """
    _check_ffmpeg()
    _check_ffprobe()


def _flat_dict(d: dict, parent_key: str = '', delimiter: str = '.') -> dict:
    items = []
    for k, v in d.items():
        new_key = parent_key + delimiter + k if parent_key else k
        if isinstance(v, dict):
            items.extend(_flat_dict(v, new_key, delimiter).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _resolve_profile_paths(name: str) -> list:
    """Resolve a profile name to an ordered list of file paths to load.

    For bare profile names (no directory component), searches both the builtin
    config directory and the user config directory (~/.estimpy/). If a profile
    exists in both locations, both are returned (builtin first, then user).

    For explicit file paths (with directory component or existing as-is),
    returns the single path directly.
    """
    # Explicit path — load as-is
    if os.path.dirname(name) or os.path.exists(name):
        if os.path.exists(name):
            return [name]
        raise Exception(f'Error: Configuration file "{name}" does not exist.')

    # Bare profile name — search builtin and user directories
    paths = []
    for search_dir in (_config_path, _user_config_path):
        for candidate in (f'{search_dir}/{name}', f'{search_dir}/{name}.yaml'):
            if os.path.exists(candidate):
                paths.append(candidate)
                break

    if not paths:
        raise Exception(f'Error: Configuration profile "{name}" does not exist.')

    return paths


def _check_config_version(profile_version: str, source: str) -> None:
    """Warn if a profile targets a newer version of estimpy than is running."""
    try:
        current = importlib.metadata.version('estimpy')
        current_parts = tuple(int(x) for x in current.split('.'))
        profile_parts = tuple(int(x) for x in str(profile_version).split('.'))
        if profile_parts > current_parts:
            print(f'Warning: Profile "{source}" targets estimpy {profile_version}, '
                  f'but running {current}.')
    except Exception:
        pass  # Version check is best-effort


def _load_config(name: str, _loading: set = None) -> None:
    """Load a configuration profile by name.

    For bare profile names, loads the builtin version first, then the user
    version (~/.estimpy/) as an overlay. After loading, processes the
    ``estimpy-version`` key (version compatibility check) and
    ``additional-config-profiles`` key (recursive profile loading).

    :param name: Profile name (bare) or file path (explicit).
    :param _loading: Set of profile names currently being loaded (cycle detection).
    """
    if _loading is None:
        _loading = set()

    # Normalize name for cycle detection (strip .yaml suffix)
    canonical = name.removesuffix('.yaml')
    if canonical in _loading:
        print(f'Warning: Skipping circular profile reference: {name}')
        return
    _loading.add(canonical)

    try:
        paths = _resolve_profile_paths(name)
        for path in paths:
            _load_config_file(path)

        # Check profile version compatibility
        version_key = 'estimpy-version'
        if version_key in cfg:
            _check_config_version(cfg[version_key], name)

        # Process additional config profiles (consumed, not persisted)
        additional_key = 'additional-config-profiles'
        additional = cfg.pop(additional_key, None)
        base_cfg.pop(additional_key, None)

        if additional:
            for profile in additional:
                _load_config(profile, _loading)
    finally:
        _loading.discard(canonical)


def _load_config_file(path: str) -> None:
    """Load a single YAML configuration file into cfg and base_cfg."""
    global cfg

    with open(path, 'r') as file_handle:
        try:
            file_cfg = _flat_dict(yaml.safe_load(file_handle), delimiter='.')

            # Store base configuration (without derived values from config.updated handlers)
            # Needed to show which configuration options can be effectively updated from the command line
            base_cfg.update(file_cfg)

            # Update the main configuration
            cfg.update(file_cfg)
        except yaml.YAMLError as exc:
            raise Exception(f'Error loading configuration file "{path}": {exc}')


load_config('default')

from . import utils, metadata, audio, analysis, player, visualization, export

trigger_event('config.updated')
