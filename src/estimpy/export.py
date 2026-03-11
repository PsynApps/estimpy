import math

import matplotlib
import matplotlib.pyplot
import os
import subprocess
import time
import tqdm

import estimpy as es

# Low DPI for export — figures are created at this DPI then resized to exact pixel dimensions,
# keeping matplotlib element proportions (fonts, lines, ticks) correct via the scale factor
_EXPORT_DPI = 8


def write_image(es_audio: es.audio.Audio, output_path: str = None, image_format: str = None,
                width: int = None, height: int = None, overwrite: bool = None,
                triphase: bool = None) -> str | None:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    image_format = es.cfg['visualization.image.export.format'] if image_format is None else image_format

    image_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.file,
        file_format=image_format
    )

    # Make sure output file is valid. Will prompt user for overwrite if appropriate.
    try:
        output_valid = es.utils.validate_output_file(output_file=image_file, overwrite=overwrite)
        if not output_valid:
            return None
    except Exception as e:
        print(e)
        return None

    width = es.cfg['visualization.image.export.width'] if width is None else width
    height = es.cfg['visualization.image.export.height'] if height is None else height

    # When triphase is explicitly overridden (e.g. video preview/album art), temporarily
    # set the image export config so the Visualization classmethods read the correct value
    triphase_key = 'visualization.image.export.triphase'
    original_triphase = es.cfg[triphase_key]
    if triphase is not None:
        es.cfg[triphase_key] = triphase
    else:
        triphase = original_triphase

    try:
        es.visualization.set_optimal_nfft(es_audio, figure_height=height,
                                          triphase=triphase,
                                          title_enabled=es.cfg['visualization.image.export.title.enabled'])

        with es.utils.Spinner(f'Preparing image visualization... '):
            visualization = es.visualization.Visualization(es_audio=es_audio, mode=es.visualization.VisualizationMode.EXPORT)
            visualization.make_figure()
            visualization.resize_figure(width=width, height=height, dpi=_EXPORT_DPI)

        with es.utils.Spinner(f'Saving image file... '):
            matplotlib.pyplot.savefig(image_file, dpi=_EXPORT_DPI, pil_kwargs={'optimize': True})

        print('Done!')

        return image_file
    finally:
        es.cfg[triphase_key] = original_triphase


def write_video(es_audio: es.audio.Audio, output_path: str = None, video_format: str = None,
                fps: float = None, width: int = None, height: int = None,
                frame_start: int = None, segment_start: int = None,
                image_file: str = None, overwrite: bool = None,
                profiling: bool = False) -> dict | None:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    video_format = video_format if video_format is not None else es.cfg['visualization.video.export.format']
    segment_start = segment_start if segment_start is not None else 1

    # Determine the number of frames per segment
    frames_per_segment = es.cfg['visualization.video.export.segment-length'] * es.cfg['visualization.video.export.fps']

    video_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.file,
        file_format=video_format
    )

    # Make sure output file is valid. Will prompt user for overwrite if appropriate.
    try:
        output_valid = es.utils.validate_output_file(output_file=video_file, overwrite=overwrite)
        if not output_valid:
            return None
    except Exception as e:
        print(e)
        return None

    video_file_base, _ = os.path.splitext(os.path.basename(video_file))

    width = es.cfg['visualization.video.export.width'] if width is None else width
    height = es.cfg['visualization.video.export.height'] if height is None else height
    image_format = es.cfg['visualization.image.export.format']

    es.visualization.set_optimal_nfft(es_audio, figure_height=height,
                                      triphase=es.cfg['visualization.video.export.triphase'],
                                      title_enabled=es.cfg['visualization.video.export.title.enabled'],
                                      include_scrub=True)

    # Set the total length of the video
    seconds_total = float(es.cfg['visualization.video.export.video-length-max']) if \
        es.cfg['visualization.video.export.video-length-max'] is not None else es_audio.length

    # Set the total number of frames
    frames_total = math.floor(seconds_total * es.cfg['visualization.video.export.fps'])

    # Set preview parameters
    preview_seconds = (
        min(es.cfg['visualization.video.export.preview.length'], seconds_total) if es.cfg['visualization.video.export.preview.enabled']
        else 0
    )
    preview_frames = preview_seconds * es.cfg['visualization.video.export.fps']
    fade_seconds = min(es.cfg['visualization.video.export.preview.fade-length'], seconds_total)

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

    # Store start time of encoding
    encoding_time_start = time.time()

    # Create animation
    for video_segment_id in video_segment_ids:
        if video_segment_id == 'preview':
            print(f'Creating video preview image...')

            # Generate preview image file (use video triphase setting, not image)
            preview_image_file = write_image(
                es_audio=es_audio,
                output_path=es.utils.get_temp_file_path(
                    temp_file_name=f'{video_file_base}-videopreview.{image_format}'
                ),
                width=width,
                height=height,
                overwrite=True,
                triphase=es.cfg['visualization.video.export.triphase']
            )

            if not preview_image_file:
                print(f'Error generating preview image file.')
                return None

            es.utils.add_temp_file(preview_image_file)

            segment_frame_start = 0

            # Value of preview frames already accounts for case where preview is longer than the file
            frame_count = preview_frames

            # Define the segment number and label to use for the progress bar
            segment_label = 'Preview segment'
        else:
            # Numeric video segment id
            try:
                video_segment_number = int(video_segment_id)
            except ValueError as e:
                print(f'Error: Unknown segment id "{video_segment_id}"')
                return None

            # Calculate the starting frame and frame count
            segment_frame_start = (video_segment_number - 1) * frames_per_segment + preview_frames
            frame_count = min(frames_total - segment_frame_start, frames_per_segment)

            # Define the segment number and label to use for the progress bar
            segment_label = f'Segment {video_segment_number}/{numeric_segments_total}'

        with es.utils.Spinner(f'Preparing video visualization for {segment_label.lower()}... '):
            visualization = es.visualization.VideoVisualization(
                es_audio=es_audio,
                fps=fps,
                frames=range(segment_frame_start, segment_frame_start + frame_count))

            visualization.make_figure(skip_initial_frame=True)
            visualization.resize_figure(width=width, height=height, dpi=_EXPORT_DPI)
            visualization.prepare_direct_render(profiling=profiling)

        # Get temporary file name to use during encoding
        # This is necessary to ensure proper handling of resuming if encoding is stopped or crashes
        video_segment_encoding_file = es.utils.get_temp_file_path(
            temp_file_name=f'{video_file_base}_{video_segment_id}-encoding.{video_format}'
        )
        # Get file name to use for segment once encoding is complete (still a temporary file)
        video_segment_file = es.utils.get_temp_file_path(
            temp_file_name=f'{video_file_base}_{video_segment_id}.{video_format}'
        )

        segment_length = frame_count * es.cfg["visualization.video.export.fps"]

        # The last frame of the segment must be a keyframe to allow concatenation without re-encoding
        ffmpeg_keyframe_args = [
            '-force_key_frames',
            f'expr:gte(t,{segment_length - 1 / es.cfg["visualization.video.export.fps"]})'
        ]

        # Initialize progress bar
        frames_progress_bar = tqdm.tqdm(total=frame_count, desc=segment_label, unit='frame')

        # Render frames directly to FFmpeg via raw video pipe
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'rgb24',
            '-r', str(es.cfg['visualization.video.export.fps']),
            '-i', 'pipe:0',
            '-c:v', es.cfg['visualization.video.export.codec'],
            *ffmpeg_extra_args,
            *ffmpeg_keyframe_args,
            video_segment_encoding_file
        ]

        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Profiling accumulators for export loop
        if profiling:
            profile_tobytes = 0.0
            profile_pipe_write = 0.0
            profile_interval = 100
            profile_count = 0

        for frame in range(segment_frame_start, segment_frame_start + frame_count):
            frame_rgb = visualization.render_frame_direct(frame)

            if profiling:
                t0 = time.perf_counter()
            frame_bytes = frame_rgb.tobytes()
            if profiling:
                profile_tobytes += time.perf_counter() - t0

                t0 = time.perf_counter()
            ffmpeg_process.stdin.write(frame_bytes)
            if profiling:
                profile_pipe_write += time.perf_counter() - t0

            frames_progress_bar.update(1)

            if profiling:
                profile_count += 1
                if profile_count >= profile_interval:
                    print(f'\n--- Export loop profile ({profile_count} frames) ---')
                    print(f'  {"tobytes":20s}: {profile_tobytes / profile_count * 1000:7.2f} ms/frame')
                    print(f'  {"pipe_write (ffmpeg)":20s}: {profile_pipe_write / profile_count * 1000:7.2f} ms/frame')
                    print()
                    profile_tobytes = 0.0
                    profile_pipe_write = 0.0
                    profile_count = 0

        ffmpeg_process.stdin.close()
        ffmpeg_process.wait()

        frames_progress_bar.close()

        # Move the temporary encoding file to the segment file name
        if os.path.exists(video_segment_file):
            os.remove(video_segment_file)
        os.rename(video_segment_encoding_file, video_segment_file)

        encoded_frames = segment_frame_start + frame_count
        encoded_time = time.time() - encoding_time_start
        encoding_fps = frame_count / (time.time() - frames_progress_bar.start_t)
        estimated_time_remaining = (frames_total - encoded_frames) / encoding_fps

        print(f'{encoded_frames}/{frames_total} frames encoded in {es.utils.seconds_to_string(encoded_time)}. Estimated time remaining: {es.utils.seconds_to_string(seconds=estimated_time_remaining)}')

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

            # Add the preview image using ffmpeg
            subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Replace the first segment with the updated version
            os.replace(src=video_file_temp_with_preview, dst=video_segment_file)

    # Prepare final video file

    # Create a temporary text file with the list of video files for ffmpeg's -f concat demuxer
    video_segment_list_file = es.utils.get_temp_file_path(f'{video_file_base}.txt')

    with open(video_segment_list_file, 'w') as f:
        for video_segment_file in video_segment_files:
            # Escape any single quotes in file name (in a very bizarre way required by ffmpeg)
            video_segment_file = video_segment_file.replace("'", "'\\''")
            # Format each line in the required 'file 'path/to/file'' format
            f.write(f'file \'{video_segment_file}\'\n')

    es.utils.add_temp_file(video_segment_list_file)

    # Determine whether to re-encode or just concatenate segments
    concat_video_codec = (
        es.cfg['visualization.video.export.codec'] if segments_total > 1 and es.cfg['visualization.video.export.reencode-segments']
        else 'copy'
    )

    # Only apply length arguments if the desired duration is shorter than the total audio file.
    # This could avoid rounding errors with the argument potentially resulting in unintended truncation of the audio
    length_args = [] if seconds_total == es_audio.length else ['-t', str(seconds_total)]

    # When stream-copying, only include global ffmpeg args (not codec-specific ones)
    if concat_video_codec == 'copy':
        # Global args that are safe regardless of codec mode
        _global_ffmpeg_args = {'-hide_banner', '-loglevel', '-y'}
        concat_extra_args = []
        i = 0
        while i < len(ffmpeg_extra_args):
            arg = ffmpeg_extra_args[i]
            if arg in _global_ffmpeg_args:
                concat_extra_args.append(arg)
                # Include the value if this arg has one
                if i + 1 < len(ffmpeg_extra_args) and not ffmpeg_extra_args[i + 1].startswith('-'):
                    concat_extra_args.append(ffmpeg_extra_args[i + 1])
                    i += 1
            i += 1
    else:
        concat_extra_args = ffmpeg_extra_args

    ffmpeg_command = [
        'ffmpeg',
        '-f', 'concat', '-safe', '0',  # "-safe 0" allows for absolute paths to files
        '-i', video_segment_list_file,
        '-i', es_audio.file,
        '-c:v', concat_video_codec,
        '-c:a', 'copy', '-strict', '-1',  # "-strict -1" allows for non-standard sample rates
        '-movflags', 'faststart',  # Improves playback and seeking efficiency
        *length_args,
        *concat_extra_args,
        video_file
    ]

    print(f'Combining segments into final video file.')

    subprocess.run(ffmpeg_command, check=True)

    try:
        print(f'Preparing metadata for video file... ')

        video_metadata = es.metadata.Metadata(file=video_file)
        video_metadata.set_metadata(es_audio.metadata.get_metadata())

        # Render an image to use as album art in the video metadata (use video triphase setting)
        if image_file is None:
            print(f'Creating album art image... ')
            image_file = write_image(es_audio=es_audio, output_path=es.utils.get_temp_file_path(),
                                     triphase=es.cfg['visualization.video.export.triphase'])
            es.utils.add_temp_file(image_file)
        image_data = open(image_file, 'rb').read()

        video_metadata.set_tag('image', image_data)

        print(f'Saving metadata to video file... ')
        video_metadata.save()
    except Exception as e:
        print(f'Warning: Failed to write metadata to video file: {e}')

    print('Deleting temporary files.')

    es.utils.delete_temp_files()

    encoding_time = time.time() - encoding_time_start
    encoding_fps = frames_total / encoding_time if encoding_time > 0 else 0
    file_size = os.path.getsize(video_file)

    print(f'Saved file "{video_file}" ({file_size}).')

    print()

    return {
        'file': video_file,
        'encoding_fps': encoding_fps,
        'total_frames': frames_total,
        'encoding_time': encoding_time,
        'file_size': file_size,
    }
