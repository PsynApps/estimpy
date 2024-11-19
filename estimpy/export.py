import datetime
import math

import matplotlib
import matplotlib.pyplot
import os
import tempfile
import time

import estimpy as es

_DPI = 8


def write_image(es_audio: es.audio.Audio, output_path: str = None, image_format: str = None,
                width: int = None, height: int = None) -> str:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    output_file_base = ''
    image_format = es.cfg['visualization.image.export.format'] if image_format is None else image_format

    if os.path.isdir(output_path):
        output_dir = output_path
    else:
        output_dir = os.path.dirname(output_path)

        if not output_dir:
            output_dir = '.'

        output_file_base, _ = os.path.splitext(os.path.basename(output_path))

    if not output_file_base:
        output_file_base, _ = os.path.splitext(os.path.basename(es_audio.file))

        # Alternatively, use metadata to set filename
        #if es_audio.metadata.artist:
        #    output_file_name += f'{es_audio.metadata.artist} - '

        #output_file_name += f'{es_audio.metadata.title}'

    image_file = f'{output_dir}/{output_file_base}.{image_format}'

    width = es.cfg['visualization.image.export.width'] if width is None else width
    height = es.cfg['visualization.image.export.height'] if height is None else height

    visualization = es.visualization.Visualization(es_audio=es_audio, mode=es.visualization.VisualizationMode.EXPORT)
    visualization.make_figure()
    visualization.resize_figure(width=width, height=height, dpi=_DPI)

    matplotlib.pyplot.savefig(image_file, dpi=_DPI, pil_kwargs={'optimize': True})

    return image_file


def write_video(es_audio: es.audio.Audio, output_path: str = None, video_format: str = None,
                fps: float = None, width: int = None, height: int = None, frame_start: int = None,
                segment_start: int = None, image_file: str = None) -> str:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    output_file_base = ''
    video_format = video_format if video_format is not None else es.cfg['visualization.video.export.format']
    frame_start = frame_start if frame_start is not None else es.cfg['visualization.video.frame-start']
    segment_start = segment_start if segment_start is not None else \
        es.cfg['visualization.video.segment-start'] if es.cfg['visualization.video.segment-start'] is not None else 1

    if os.path.isdir(output_path):
        output_dir = output_path
    else:
        output_dir = os.path.dirname(output_path)

        if not output_dir:
            output_dir = '.'

        output_file_base, _ = os.path.splitext(os.path.basename(output_path))

    if not output_file_base:
        output_file_base, _ = os.path.splitext(os.path.basename(es_audio.file))

        # Alternatively, use metadata to set filename
        # if es_audio.metadata.artist:
        #    output_file_name += f'{es_audio.metadata.artist} - '

        # output_file_name += f'{es_audio.metadata.title}'

    video_file = f'{output_dir}/{output_file_base}.{video_format}'

    width = es.cfg['visualization.video.export.width'] if width is None else width
    height = es.cfg['visualization.video.export.height'] if height is None else height
    image_format = es.cfg['visualization.image.export.format']

    if image_file is None:
        image_file = write_image(es_audio=es_audio, output_path=tempfile.gettempdir())
        es.utils.add_temp_file(image_file)
    image_data = open(image_file, 'rb').read()

    preview_image_file = None
    if es.cfg['visualization.video.export.preview.enabled']:
        preview_image_file = write_image(
            es_audio=es_audio,
            output_path=tempfile.gettempdir() + f'/{output_file_base}-videopreview.{image_format}',
            width=width,
            height=height)
        es.utils.add_temp_file(preview_image_file)

    frames_total = math.floor(es_audio.length * es.cfg['visualization.video.export.fps'])
    segments_total = math.floor(frames_total / es.cfg['visualization.video.export.frames-per-segment']) + 1

    if frame_start is not None:
        segment_start = math.floor(frame_start / es.cfg['visualization.video.export.frames-per-segment']) + 1

    segment_start_frame = (segment_start - 1) * es.cfg['visualization.video.export.frames-per-segment']

    def progress_callback(i, n):
        if i % es.cfg['visualization.video.export.fps'] == 0:
            print(f" Saving frame: {segment_start_frame + i}/{frames_total} ({i}/{n} in segment {math.floor((segment_start_frame + i) / es.cfg['visualization.video.export.frames-per-segment']) + 1}/{segments_total})")

    # Process all extra ffmpeg extra argument key/value pairs into a list to be used by animation.save()
    ffmpeg_extra_args = []

    # Configuration key prefix for ffmpeg extra arguments
    ffmpeg_extra_args_cfg_prefix = 'visualization.video.export.ffmpeg-extra-args.'

    # Iterate through the configuration to find ffmpeg extra args
    for arg_name_key, arg_value in es.cfg.items():
        if arg_name_key.startswith(ffmpeg_extra_args_cfg_prefix):
            # Extract the argument name from the configuration key
            arg_name = arg_name_key[len(ffmpeg_extra_args_cfg_prefix):]
            # Add the argument name and value to the argument list if it is not None
            if arg_value is not None:
                ffmpeg_extra_args.extend([arg_name, str(arg_value)])

    # Convert extra arguments into string for use by subsequent system calls to ffmpeg
    ffmpeg_extra_args_string = ' '.join(str(arg) for arg in ffmpeg_extra_args)

    # Create animation
    for i_video_file in range(segment_start, segments_total + 1):
        print(f'Preparing video file {i_video_file}/{segments_total}:')

        i_time_start = time.time()
        frame_count = min(frames_total - segment_start_frame, es.cfg['visualization.video.export.frames-per-segment'])

        video_file_temp = tempfile.gettempdir() + f'/{output_file_base}_{i_video_file}.{video_format}'
        es.utils.add_temp_file(video_file_temp)

        visualization = es.visualization.VideoVisualization(
            es_audio=es_audio,
            fps=fps,
            frames=range(segment_start_frame, segment_start_frame + frame_count))

        visualization.make_figure()
        visualization.resize_figure(width=width, height=height, dpi=_DPI)

        visualization.animation.save(
            video_file_temp,
            writer='ffmpeg',
            fps=es.cfg['visualization.video.export.fps'],
            codec=es.cfg['visualization.video.export.codec'],
            extra_args=ffmpeg_extra_args,
            progress_callback=progress_callback)

        segment_start_frame += es.cfg['visualization.video.export.frames-per-segment']

        i_time_length = time.time() - i_time_start
        i_fps = frame_count / i_time_length

        print(f"Wrote {frame_count} frames in {es.utils.seconds_to_string(seconds=i_time_length)} ({i_fps:.1f} FPS).")

        if i_video_file < segments_total:
            print(
                f"Estimated time remaining: {es.utils.seconds_to_string(seconds=(frames_total - segment_start_frame) / i_fps)}")

        print("")

    if segments_total > 1:
        print(f"Combining {segments_total} segments into single video file.")
        ffmpeg_concat_inputs = ''
        ffmpeg_concat_filter = ''
        for i_video_file in range(1, segments_total + 1):
            video_file_temp = tempfile.gettempdir() + f'/{output_file_base}_{i_video_file}.{video_format}'

            video_file_temp_escaped = video_file_temp.replace('"', '\"')
            ffmpeg_concat_inputs += f'-i "{video_file_temp_escaped}" '
            ffmpeg_concat_filter += f'[{i_video_file - 1}:v] '

        video_file_noaudio = tempfile.gettempdir() + f'/{output_file_base}_noaudio.{video_format}'
        video_file_noaudio_escaped = video_file_noaudio.replace('"', '\"')

        os.system(
            f'{es.cfg["visualization.video.export.ffmpeg"]} {ffmpeg_concat_inputs} {ffmpeg_extra_args_string} -c:v {es.cfg["visualization.video.export.codec"]} -filter_complex "{ffmpeg_concat_filter} concat=n={segments_total}:v=1 [v]" -map "[v]" "{video_file_noaudio_escaped}"')
        print("")

        es.utils.add_temp_file(video_file_noaudio)
    else:
        video_file_noaudio_escaped = tempfile.gettempdir() + f'/{output_file_base}_1.{video_format}'

    if preview_image_file:
        print(f"Adding preview image to beginning of video.")
        video_preview_image_file_escaped = preview_image_file.replace('"', '\"')
        preview_seconds = min(es.cfg['visualization.video.export.preview.length'], es_audio.length)
        fade_seconds = min(es.cfg['visualization.video.export.preview.fade-length'], es_audio.length)

        video_file_preview = tempfile.gettempdir() + f'/{output_file_base}_withpreview.{video_format}'
        video_file_preview_escaped = video_file_preview.replace('"', '\"')

        os.system(
            f'{es.cfg["visualization.video.export.ffmpeg"]} -i "{video_file_noaudio_escaped}" -loop 1 -t {preview_seconds} -i "{video_preview_image_file_escaped}" {ffmpeg_extra_args_string} -c:v {es.cfg["visualization.video.export.codec"]} -filter_complex "[1:v]fade=t=out:st={preview_seconds - fade_seconds}:d={fade_seconds}:alpha=1[i]; [0:v][i]overlay=0:0:enable=\'between(t,0,{preview_seconds})\'" "{video_file_preview_escaped}"')
        print("")

        es.utils.add_temp_file(video_file_preview)

        # Change the file reference to use as the input to merge with the audio file
        video_file_noaudio_escaped = video_file_preview_escaped

    print(f"Adding audio track to video file.")
    file_escaped = es_audio.file.replace('"', '\"')
    video_file_escaped = video_file.replace('"', '\"')

    os.system(
        f'{es.cfg["visualization.video.export.ffmpeg"]} -i "{video_file_noaudio_escaped}" -i "{file_escaped}" -c:v copy -c:a copy "{video_file_escaped}"')
    print("")

    print("Saving video metadata.")
    video_metadata = es.metadata.Metadata(file=video_file)
    video_metadata.set_metadata(es_audio.metadata.get_metadata())
    video_metadata.set_tag('image', image_data)
    video_metadata.save()

    print("Deleting temporary files.")
    es.utils.delete_temp_files()

    return video_file
