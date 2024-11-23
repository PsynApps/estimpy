import datetime
import math
import sys

import matplotlib
import matplotlib.pyplot
import os
import subprocess
import time

import estimpy as es

_DPI = 8


def write_image(es_audio: es.audio.Audio, output_path: str = None, image_format: str = None,
                width: int = None, height: int = None) -> str | None:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    image_format = es.cfg['visualization.image.export.format'] if image_format is None else image_format

    image_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.file,
        file_format=image_format
    )

    width = es.cfg['visualization.image.export.width'] if width is None else width
    height = es.cfg['visualization.image.export.height'] if height is None else height

    visualization = es.visualization.Visualization(es_audio=es_audio, mode=es.visualization.VisualizationMode.EXPORT)
    visualization.make_figure()
    visualization.resize_figure(width=width, height=height, dpi=_DPI)

    matplotlib.pyplot.savefig(image_file, dpi=_DPI, pil_kwargs={'optimize': True})

    return image_file


def write_video(es_audio: es.audio.Audio, output_path: str = None, video_format: str = None,
                fps: float = None, width: int = None, height: int = None, frame_start: int = None,
                segment_start: int = None, image_file: str = None) -> str | None:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    video_format = video_format if video_format is not None else es.cfg['visualization.video.export.format']
    frame_start = frame_start if frame_start is not None else es.cfg['visualization.video.frame-start']
    segment_start = segment_start if segment_start is not None else \
        es.cfg['visualization.video.segment-start'] if es.cfg['visualization.video.segment-start'] is not None else 1

    # Determine the number of frames per segment
    frames_per_segment = es.cfg['visualization.video.export.segment-length'] * es.cfg['visualization.video.export.fps']

    video_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.file,
        file_format=video_format
    )
    video_file_base, _ = os.path.splitext(os.path.basename(video_file))

    width = es.cfg['visualization.video.export.width'] if width is None else width
    height = es.cfg['visualization.video.export.height'] if height is None else height
    image_format = es.cfg['visualization.image.export.format']

    # Set the total number of frames
    frames_total = math.floor(es_audio.length * es.cfg['visualization.video.export.fps'])

    # Set preview parameters
    preview_seconds = (
        min(es.cfg['visualization.video.export.preview.length'], es_audio.length) if es.cfg['visualization.video.export.preview.enabled']
        else 0
    )
    preview_frames = preview_seconds * es.cfg['visualization.video.export.fps']
    fade_seconds = min(es.cfg['visualization.video.export.preview.fade-length'], es_audio.length)

    # If a starting frame is specified rather than a segment, determine the starting segment based upon the frame
    if frame_start is not None:
        segment_start = max(math.floor((frame_start - preview_frames) / frames_per_segment) + 1, 1)

    # Generate list of video segments
    video_segment_ids = []

    if es.cfg['visualization.video.export.preview.enabled']:
        video_segment_ids.append('preview')

    # Create segment ids for all remaining segments
    numeric_video_segments = [str(i) for i in range(1, math.floor((frames_total - preview_frames) / frames_per_segment) + 2)]
    numeric_segments_total = len(numeric_video_segments)
    video_segment_ids.extend(numeric_video_segments)

    # Get the total number of video segments
    segments_total = len(video_segment_ids)

    current_segment = 1

    # Initialize list of video segment files
    video_segment_files = []

    print('')

    # Gather previously processed files if resuming (not starting with the first segment)
    if segment_start > 1:
        # Iterate over the segments to process completed files
        # Use a copy of the list of segments so we can remove completed segments from the main list
        for video_segment_id in video_segment_ids[:]:
            # If the current segment is the start segment, exit the loop
            try:
                if segment_start == int(video_segment_id):
                    break
            except ValueError as e:
                pass

            # Get the full path to the previously processed file
            video_segment_file = es.utils.get_temp_file_path(
                temp_file_name=f'{video_file_base}_{video_segment_id}.{video_format}'
            )

            # Make sure the previously processed file exists
            if not os.path.isfile(video_segment_file):
                print(
                    f'Error: Could not resume writing video, file for segment {video_segment_id} not found ("{video_segment_file}").')
                return None

            # Add segment file to appropriate lists
            video_segment_files.append(video_segment_file)
            es.utils.add_temp_file(video_segment_file)

            # Remove the segment id from the list to be encoded
            video_segment_ids.remove(video_segment_id)
            current_segment += 1

    # Process all extra ffmpeg extra argument key/value pairs into a list to be used by animation.save()
    ffmpeg_extra_args = []

    # Set the maximum keyframe interval if defined
    if es.cfg['visualization.video.export.keyframe-interval'] is not None:
        ffmpeg_extra_args.extend([
            '-g',
            str(es.cfg['visualization.video.export.keyframe-interval'] * es.cfg['visualization.video.export.fps'])
        ])

    # Configuration key prefix for ffmpeg extra arguments
    ffmpeg_extra_args_cfg_prefix = 'visualization.video.export.ffmpeg-extra-args.'

    # Iterate through the configuration to find ffmpeg extra args
    for arg_name_key, arg_value in es.cfg.items():
        if arg_name_key.startswith(ffmpeg_extra_args_cfg_prefix):
            # Extract the argument name from the configuration key
            arg_name = arg_name_key[len(ffmpeg_extra_args_cfg_prefix):]
            # Add the argument name and value to the argument list if it is not None
            if arg_value is not None:
                ffmpeg_extra_args.append(arg_name)
                if arg_value != '':
                    ffmpeg_extra_args.append(str(arg_value))

    total_start_time = time.time()
    global callback_time

    # Create animation
    for video_segment_id in video_segment_ids:
        segment_time_start = time.time()

        if video_segment_id == 'preview':
            # print(f'Preparing preview segment')

            # Generate preview image file
            preview_image_file = write_image(
                es_audio=es_audio,
                output_path=es.utils.get_temp_file_path(
                    temp_file_name=f'{video_file_base}-videopreview.{image_format}'
                ),
                width=width,
                height=height,
            )

            if not preview_image_file:
                print(f'Error generating preview image file.')
                return None

            es.utils.add_temp_file(preview_image_file)

            segment_frame_start = 0

            # Value of preview frames already accounts for case where preview is longer than the file
            segment_frame_count = preview_frames
        else:
            # Numeric video segment id
            try:
                video_segment_number = int(video_segment_id)
            except ValueError as e:
                print(f'Error: Unknown segment id "{video_segment_id}"')
                return None

            # print(f'Preparing video segment {len(video_segment_files)}/{numeric_segments_total}:')

            segment_frame_start = (video_segment_number - 1) * frames_per_segment + preview_frames
            segment_frame_count = min(frames_total - segment_frame_start, frames_per_segment)



        def progress_callback(i, n):
            global callback_time
            if i == 1:
                callback_time = time.time() - callback_time
            if i > 2:
                # Smoothly update callback_time with a moving average
                callback_time = ((callback_time * (i - 1)) + (time.time() - segment_time_start) / i) / i

            # Estimate remaining time (ETA)
            remaining_frames = segment_frame_count - i
            segment_eta = "..." if i < 2 else f"{es.utils.seconds_to_string(callback_time * remaining_frames)}"
            total_eta = "..." if i < 2 else f"{es.utils.seconds_to_string(callback_time * (frames_total - segment_frame_start - i))}"
            time_elapsed = f"{es.utils.seconds_to_string(time.time() - total_start_time)}"

            frame_width = len(f"{segment_frame_start + segment_frame_count}/{frames_total}")
            eta_width = len(segment_eta)
            elapsed_width = len(time_elapsed)
            fps_width = len(f"{(1 / callback_time):2.1f}")

            # Frame progress formatting
            # if video_segment_id == 'preview':
            #     frame = f'{segment_frame_start + i:>3}/{segment_frame_count}{len(f'({i:>3}/{n:>3} in segment {current_segment}/{numeric_segments_total})')*' '+' '}'
            # else:
            #     frame = f'{segment_frame_start + i:>3}/{frames_total} ({i:>3}/{n:>3} in segment {current_segment}/{numeric_segments_total})'
            frame = f'{segment_frame_start + i:>3}/{frames_total} ({i:>3}/{n:>3} in segment)'

            # Calculate progress percentage
            percent = int((i / segment_frame_count) * 100) if i < segment_frame_count else 100

            # Create progress bar using Unicode blocks
            bar_length = 50
            filled_length = percent * bar_length // 100
            bar = '█' * filled_length + '░' * (bar_length - filled_length)

            # In-place update with a carriage return
            #sys.stdout.write(f"\rFrame: {frame: <7}: {bar} {percent: >3}%,  Segment ETA: {segment_eta:>8},  Total ETA: {total_eta:>8},  Time elapsed: {time_elapsed:>8},  FPS: {(1/callback_time):2.1f}")
            sys.stdout.write(
                f"\r"
                f"{'Preview segment' if video_segment_id == 'preview' else f'Segment {current_segment}/{numeric_segments_total}': <20}"
                f"Frame: {frame: <{frame_width}}: "
                f"{bar} "
                f"{percent: >3}%, "
                f"Time elapsed: {time_elapsed: >{elapsed_width}}, "
                f"Segment ETA: {segment_eta: >{eta_width}}, "
                f"Total ETA: {total_eta: >{eta_width}}, "
                f"FPS: {(1 / callback_time): >{fps_width}.1f} "
            )
            # sys.stdout.write(
            #     f"\r"
            #     f"Frame: {frame: <{frame_width}}: "
            #     f"{bar} "
            #     f"{percent: >3}%, "
            #     f"Time elapsed: {time_elapsed: >{elapsed_width}}, "
            #     f"Segment ETA: {segment_eta: >{eta_width}}, "
            #     f"Total ETA: {total_eta: >{eta_width}}, "
            #     f"FPS: {(1 / callback_time): >{fps_width}.1f} "
            # )
            sys.stdout.flush()
            if i == frames_total:
                sys.stdout.write("\n")

        # print('Preparing animation for next segment...')
        visualization = es.visualization.VideoVisualization(
            es_audio=es_audio,
            fps=fps,
            frames=range(segment_frame_start, segment_frame_start + segment_frame_count))

        visualization.make_figure()
        visualization.resize_figure(width=width, height=height, dpi=_DPI)

        video_segment_file = es.utils.get_temp_file_path(
            temp_file_name=f'{video_file_base}_{video_segment_id}.{video_format}'
        )

        segment_length = segment_frame_count * es.cfg["visualization.video.export.fps"]

        # The last frame of the segment must be a keyframe to allow concatenation without re-encoding
        ffmpeg_keyframe_args = [
            '-force_key_frames',
            f'expr:gte(t,{segment_length - 1 / es.cfg["visualization.video.export.fps"]})'
        ]

        callback_time = time.time()

        visualization.animation.save(
            video_segment_file,
            writer='ffmpeg',
            fps=es.cfg['visualization.video.export.fps'],
            codec=es.cfg['visualization.video.export.codec'],
            extra_args=ffmpeg_extra_args + ffmpeg_keyframe_args,
            progress_callback=progress_callback)

        # Call one last time to update progress bar to 100%
        progress_callback(segment_frame_count, segment_frame_count)

        video_segment_files.append(video_segment_file)
        es.utils.add_temp_file(video_segment_file)

        # Additional processing for preview segment
        if video_segment_id == 'preview':
            video_file_temp_with_preview = es.utils.get_temp_file_path(
                temp_file_name=f'{video_file_base}_{video_segment_id}-withfade.{video_format}'
            )

            ffmpeg_command = [
                'ffmpeg',
                '-i', video_segment_file,
                '-loop', '1', '-t', str(preview_seconds), '-i', preview_image_file,
                '-filter_complex',
                f'[1:v]fade=t=out:st={preview_seconds - fade_seconds}:d={fade_seconds}:alpha=1[faded]; '
                f'[0:v][faded]overlay=0:0:enable=\'between(t,0,{preview_seconds})\'[output]',
                '-map', '[output]',
                '-r', str(es.cfg['visualization.video.export.fps']),
                '-c:v', es.cfg['visualization.video.export.codec'],
                *(ffmpeg_extra_args + ffmpeg_keyframe_args),
                video_file_temp_with_preview
            ]

            # Debug print for constructed command
            #print("FFmpeg command:", ' '.join(ffmpeg_command))

            # Add the preview image using ffmpeg
            subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Replace the first segment with the updated version
            os.replace(src=video_file_temp_with_preview, dst=video_segment_file)
        else:
            current_segment += 1

        segment_time_length = time.time() - segment_time_start
        segment_time_fps = segment_frame_count / segment_time_length

        print('')
        # print(
        #     f'Wrote {segment_frame_count} frames in {es.utils.seconds_to_string(seconds=segment_time_length)} ({segment_time_fps:.1f} FPS).')

        # If not the preview or last segment, show estimated time remaining
        # if video_segment_id != 'preview' and video_segment_id != video_segment_ids[-1]:
        #     print(
        #         f'Estimated time remaining: {es.utils.seconds_to_string(seconds=(frames_total - segment_frame_start) / segment_time_fps)}')

        # print('')

    # Prepare final video file

    # Create a temporary text file with the list of video files for ffmpeg's -f concat demuxer
    video_segment_list_file = es.utils.get_temp_file_path(f'{video_file_base}.txt')

    with open(video_segment_list_file, 'w') as f:
        for video_segment_file in video_segment_files:
            # Format each line in the required 'file 'path/to/file'' format
            f.write(f'file \'{video_segment_file}\'\n')

    es.utils.add_temp_file(video_segment_list_file)

    # Determine whether to re-encode or just concatenate segments
    concat_video_codec = (
        es.cfg['visualization.video.export.codec'] if segments_total > 1 and es.cfg['visualization.video.export.reencode-segments']
        else 'copy'
    )

    ffmpeg_command = [
        'ffmpeg',
        '-f', 'concat', '-safe', '0',  # "-safe 0" allows for absolute paths to files
        '-i', video_segment_list_file,
        '-i', es_audio.file,
        '-c:v', concat_video_codec,
        '-c:a', 'copy', '-strict', '-1',  # "-strict -1" allows for non-standard sample rates
        '-movflags', 'faststart',  # Improves playback and seeking efficiency
        *ffmpeg_extra_args,
        video_file
    ]

    print('')
    print(f'Combining segments into final video file.')

    # Debug print for constructed command
    #print('FFmpeg command:', ' '.join(ffmpeg_command))

    subprocess.run(ffmpeg_command, check=True)

    print('')

    print('Saving video metadata.')
    video_metadata = es.metadata.Metadata(file=video_file)
    video_metadata.set_metadata(es_audio.metadata.get_metadata())

    # Render an image to use as album art in the video metadata
    if image_file is None:
        image_file = write_image(es_audio=es_audio, output_path=es.utils.get_temp_file_path())
        es.utils.add_temp_file(image_file)
    image_data = open(image_file, 'rb').read()
    
    video_metadata.set_tag('image', image_data)
    video_metadata.save()

    print('Deleting temporary files.')
    es.utils.delete_temp_files()

    return video_file
