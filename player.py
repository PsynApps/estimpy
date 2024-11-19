import argparse
import logging
import tkinter as tk
import tkinter.filedialog

import estimpy as es

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description='Provides a real-time player for Estim audio files with visual rendering of various audio analyses and independent control of channel volume output.')

    es.utils.add_parser_arguments(parser, ['input_files', 'recursive', 'config',
                                           'dynamic_range', 'frequency_min', 'frequency_max'])

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
