import argparse
import logging
import sys
import tkinter as tk
import tkinter.filedialog

import estimpy as es

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description='Generates various forms of visualization for Estim media files')
    parser.add_argument('-si', '--show-image', action='store_true',
                        help='Show a window with an image visualization of the input file(s). This is the default behavior if no action is specified.')
    parser.add_argument('-wi', '--write-image', action='store_true',
                        help='Save an image file with visualization of the input file(s). Files will be saved using the same base file name as the input file.')
    parser.add_argument('-wm', '--write-metadata', action='store_true',
                        help='Modify the input file(s) to add or replace the album art metadata with the image visualization. This is only supported for mp3, mp4, and m4a files.')
    parser.add_argument('-wv', '--write-video', action='store_true',
                        help='Save a video file with an animated visualization of the input file(s). Files will use the audio track from the input file and be saved using the same base file name as the input file.')

    es.utils.add_parser_arguments(parser, es.utils.get_default_parser_arguments() + ['output_path'])

    parser.add_argument('-rf', '--resume-frame', default=None, type=int,
                        help='Frame on which to resume video encoding. Only relevant for the write-video action. Useful if script crashes during a large encoding.')

    parser.add_argument('-rs', '--resume-segment', default=None, type=int,
                        help='Segment on which to resume video encoding. Only relevant for the write-video action. Useful if script crashes during a large encoding. Will not work correctly if segment-length configuration value is changed between runs.')

    parser.add_argument('-y', '--yes', action='store_true',
                        help='Answers yes to all interactive prompts (overwrites files by default).')

    args = vars(parser.parse_args())

    es.utils.handle_parser_arguments(args)

    input_files = args['input_files']

    if not input_files:
        input_files = tk.filedialog.askopenfilenames(initialdir='.', title='Select file(s)')

    if not input_files:
        sys.exit()

    actions = {
        'show-image': args['show_image'],
        'write-image': args['write_image'],
        'write-metadata': args['write_metadata'],
        'write-video': args['write_video'],
    }
    if not any(actions.values()):
        actions['show-image'] = True

    resume_frame = args['resume_frame']
    resume_segment = args['resume_segment']

    if args['yes']:
        es.cfg['files.output.overwrite-default'] = True

    # Get list of input files
    files = es.utils.get_file_list(file_patterns=input_files)

    # Main loop
    for file in files:
        spinner = es.utils.Spinner(f'Loading file {file}... ')
        es_audio = es.audio.Audio(file=file)
        spinner.stop()

        image_file = None

        if actions['write-image']:
            image_file = es.export.write_image(es_audio=es_audio)

        if actions['write-metadata']:
            try:
                es.metadata.write_metadata(es_audio=es_audio, image_file=image_file)
            except Exception as e:
                print(e)

        if actions['write-video']:
            video_file = es.export.write_video(
                es_audio=es_audio, image_file=image_file,
                frame_start=resume_frame, segment_start=resume_segment)

        if actions['show-image']:
            es.visualization.show_image(es_audio=es_audio)
