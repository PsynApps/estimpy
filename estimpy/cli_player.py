"""
Player CLI

This script serves as the command-line entry point for the EstimPy audio player tool.
It provides a user-friendly interface for playing Estim audio files.

Usage:
    Run via the command line using `estimpy-visualizer`.
"""

import argparse
import logging
import tkinter as tk
import tkinter.filedialog

import estimpy as es


def main():
    logging.getLogger().setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description='Provides a real-time player for Estim audio files with visual rendering of various audio analyses and independent control of channel volume output.')

    es.utils.add_parser_arguments(parser, es.utils.get_default_parser_arguments())

    args = vars(parser.parse_args())

    es.utils.handle_parser_arguments(args)

    input_files = args['input_files']

    if not input_files:
        input_files = tk.filedialog.askopenfilenames(initialdir='.', title='Select file(s)')

    recursive = args['recursive']

    # Get list of input files
    audio_files = es.utils.get_file_list(file_patterns=input_files, recursive=recursive)

    video_player = es.player.Player(audio_files=audio_files)
    video_player.show()


if __name__ == '__main__':
    main()
