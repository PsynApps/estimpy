import math

import matplotlib
import matplotlib.pyplot
import os
import subprocess
import time
import tqdm
from PIL import Image, ImageDraw, ImageFont

import estimpy as es

# Low DPI for export — figures are created at this DPI then resized to exact pixel dimensions,
# keeping matplotlib element proportions (fonts, lines, ticks) correct via the scale factor
_EXPORT_DPI = 8

# Maps file extensions to FFmpeg encoder names for audio codec autodetection
_EXTENSION_CODEC_MAP = {
    'mp3': 'libmp3lame',
    'flac': 'flac',
    'wav': 'pcm_s24le',
    'm4a': 'aac',
    'aac': 'aac',
    'ogg': 'libvorbis',
    'opus': 'libopus',
}

# Maps FFmpeg encoder names to their natural file extensions
_CODEC_FORMAT_MAP = {
    'libmp3lame': 'mp3',
    'flac': 'flac',
    'pcm_s16le': 'wav',
    'pcm_s24le': 'wav',
    'pcm_s32le': 'wav',
    'aac': 'm4a',
    'libvorbis': 'ogg',
    'libopus': 'opus',
}

# Sensible quality defaults applied when codec is auto-resolved and no explicit
# ffmpeg-extra-args are configured. Keyed by FFmpeg encoder name.
_AUTO_QUALITY_ARGS = {
    'libmp3lame': ['-q:a', '0'],
    'aac': ['-b:a', '256k'],
    'libvorbis': ['-q:a', '8'],
    'libopus': ['-b:a', '256k'],
}

# Audio codecs that are widely supported in each video container format.
# Codecs not in this set may cause playback issues on some devices/players.
_CONTAINER_SAFE_AUDIO_CODECS = {
    'mp4': {'aac', 'libmp3lame', 'mp3', 'ac3', 'eac3'},
    'mov': {'aac', 'libmp3lame', 'mp3', 'ac3', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le'},
}

# Default audio codec to use when re-encoding audio for a video container
_CONTAINER_DEFAULT_AUDIO_CODEC = {
    'mp4': 'aac',
    'mov': 'aac',
}


def _build_ffmpeg_extra_args(cfg_prefix: str) -> list:
    """Build an FFmpeg argument list from config keys under the given prefix.

    Iterates through all config keys starting with ``cfg_prefix``, extracting the
    argument name from the key suffix and its value. Keys with None values are skipped.
    Empty-string values emit only the argument name (flag-style).

    :param cfg_prefix: Config key prefix ending with a dot, e.g. ``'video.export.ffmpeg-extra-args.'``.
    :return list: Flat list of FFmpeg argument strings.
    """
    args = []
    for key, value in es.cfg.items():
        if key.startswith(cfg_prefix):
            arg_name = key[len(cfg_prefix):]
            if value is not None:
                args.append(arg_name)
                if value != '':
                    args.append(str(value))
    return args


def _draw_ss_badge_on_image(image_path, fig_width, fig_height, time_enabled, time_position):
    """Draw the SS badge onto a saved image file if stereo stim mode is enabled."""
    if not es.cfg['audio.stereo-stim.enabled']:
        return

    import matplotlib.colors

    font_file = es.cfg['visualization.style.font.text.file']
    face_index = es.cfg['visualization.style.font.text.face-index']

    # Scale to visually match time text — compute the time text pixel size from the
    # figure resize math, then apply 0.8x to account for the stroke border that makes
    # the time text appear larger than raw font metrics
    display_height = es.cfg['visualization.image.display.height']
    time_font_pt = es.cfg['visualization.style.time.font-size']
    time_font_size_px = int(time_font_pt * fig_height * 100 / (display_height * 72))
    badge_font_size = max(8, int(time_font_size_px * 0.8))
    badge_font = ImageFont.truetype(font_file, badge_font_size, index=face_index)

    # Use axes color for text and outline
    axes_color_rgb = matplotlib.colors.to_rgb(es.cfg['visualization.style.axes.color'])
    axes_color = tuple(int(c * 255) for c in axes_color_rgb) + (255,)

    # Measure text
    dummy = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), 'SS', font=badge_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x = max(4, badge_font_size // 3)
    pad_y = max(2, badge_font_size // 5)
    badge_w = tw + 2 * pad_x
    badge_h = th + 2 * pad_y

    # Create badge
    badge_img = Image.new('RGBA', (badge_w, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge_img)
    radius = max(3, badge_h // 3)
    draw.rounded_rectangle(
        [(0, 0), (badge_w - 1, badge_h - 1)],
        radius=radius, fill=(0, 0, 0, 0), outline=axes_color, width=1)
    draw.text(
        (pad_x - bbox[0], pad_y - bbox[1]),
        'SS', font=badge_font, fill=axes_color)

    # Position: to the left of where the time text would be
    margin = max(2, badge_font_size // 4)
    position_top = (time_position == 'top')
    if time_enabled:
        # Estimate time text rendered size (at the full time font pixel size, not the
        # scaled-down badge size) to find the time text position on the image
        time_font = ImageFont.truetype(font_file, time_font_size_px, index=face_index)
        time_bbox = draw.textbbox((0, 0), '00:00.0', font=time_font,
                                  stroke_width=max(1, int(es.cfg['visualization.style.font.text.border-width']
                                                          * fig_height * 100 / (display_height * 72))))
        time_w = time_bbox[2] - time_bbox[0]
        time_h = time_bbox[3] - time_bbox[1]
        time_margin = max(2, time_font_size_px // 8)
        time_x = fig_width - time_w - time_margin
        time_y = time_margin if position_top else fig_height - time_h - time_margin
        gap = max(4, badge_font_size // 2)
        bx = time_x - badge_w - gap
        by = time_y + (time_h - badge_h) // 2  # vertically center with time text
        by = max(time_margin, by)  # ensure same minimum edge margin as time text
    else:
        bx = fig_width - badge_w - margin
        by = margin if position_top else fig_height - badge_h - margin

    # Composite onto image
    img = Image.open(image_path).convert('RGBA')
    img.paste(badge_img, (max(0, bx), max(0, by)), badge_img)
    img.convert('RGB').save(image_path)


def _detect_source_audio_codec(es_audio: es.audio.Audio) -> str | None:
    """Detect the audio codec of the original source file via FFprobe.

    :return str | None: FFmpeg encoder name, or None if detection fails.
    """
    _codec_map = {
        'mp3': 'libmp3lame',
        'aac': 'aac',
        'vorbis': 'libvorbis',
        'opus': 'libopus',
        'flac': 'flac',
        'pcm_s16le': 'pcm_s16le',
        'pcm_s24le': 'pcm_s24le',
        'pcm_s32le': 'pcm_s32le',
    }

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_name', '-of', 'csv=p=0',
             es_audio.metadata.file],
            capture_output=True, text=True, timeout=10)
        codec = result.stdout.strip().rstrip(',')
        return _codec_map.get(codec)
    except Exception:
        return None


def _is_audio_modified() -> bool:
    """Check whether the audio processing chain has modified the audio data."""
    return (es.cfg['audio.stereo-stim.enabled']
            or es.cfg['audio.ramp.level'] > 0
            or es.cfg['audio.frequency.scale'] != 1
            or es.cfg['audio.frequency.shift'] != 0)


def _resolve_audio_codec(es_audio: es.audio.Audio, output_file: str = None) -> str:
    """Resolve the audio codec to use for encoding.

    Resolution priority:
    1. Explicit config value (``audio.export.codec`` is not None) — use it.
    2. Output file extension — infer codec from the extension.
    3. Source file codec — detect and match the input file's codec.
    4. Fallback — ``libmp3lame``.

    :param es_audio: Audio instance to detect source codec from.
    :param output_file: Output file path (used for extension-based inference).
    :return str: FFmpeg encoder name.
    """
    # 1. Explicit config
    configured = es.cfg['audio.export.codec']
    if configured is not None:
        return configured

    # 2. Output file extension
    if output_file:
        ext = os.path.splitext(output_file)[1].lstrip('.').lower()
        if ext in _EXTENSION_CODEC_MAP:
            return _EXTENSION_CODEC_MAP[ext]

    # 3. Source file codec
    detected = _detect_source_audio_codec(es_audio)
    if detected:
        return detected

    # 4. Fallback
    return 'libmp3lame'


def _resolve_audio_format(es_audio: es.audio.Audio, codec: str) -> str:
    """Resolve the audio output format (container/extension).

    Resolution priority:
    1. Explicit config value (``audio.export.format`` is not None) — use it.
    2. Infer from the resolved codec.
    3. Source file extension.
    4. Fallback — ``mp3``.

    :param es_audio: Audio instance to detect source format from.
    :param codec: The resolved codec (used for format inference).
    :return str: File extension string (e.g. ``'mp3'``, ``'flac'``).
    """
    # 1. Explicit config
    configured = es.cfg['audio.export.format']
    if configured is not None:
        return configured

    # 2. Infer from codec
    if codec in _CODEC_FORMAT_MAP:
        return _CODEC_FORMAT_MAP[codec]

    # 3. Source file extension
    if es_audio.source_file:
        ext = os.path.splitext(es_audio.source_file)[1].lstrip('.').lower()
        if ext:
            return ext

    # 4. Fallback
    return 'mp3'


def _resolve_audio_extra_args(codec: str) -> list:
    """Resolve FFmpeg extra arguments for audio encoding.

    If explicit ``audio.export.ffmpeg-extra-args`` are configured, those are used.
    Otherwise, sensible quality defaults are applied based on the codec.

    :param codec: The resolved FFmpeg encoder name.
    :return list: Flat list of FFmpeg argument strings.
    """
    configured_args = _build_ffmpeg_extra_args('audio.export.ffmpeg-extra-args.')
    if configured_args:
        return configured_args

    return list(_AUTO_QUALITY_ARGS.get(codec, []))


def _resolve_video_audio_codec(es_audio: es.audio.Audio) -> list:
    """Resolve the audio codec arguments for the video export concat step.

    When audio is unmodified and the source codec is compatible with the video
    container, stream-copies the audio. Otherwise re-encodes using the configured
    or container-appropriate codec.

    :param es_audio: Audio instance.
    :return list: FFmpeg arguments for the audio codec (e.g. ``['-c:a', 'copy']``).
    """
    video_format = es.cfg['video.export.format']
    safe_codecs = _CONTAINER_SAFE_AUDIO_CODECS.get(video_format)
    container_default = _CONTAINER_DEFAULT_AUDIO_CODEC.get(video_format, 'aac')

    # Check if an explicit audio codec was configured
    configured_codec = es.cfg['audio.export.codec']

    if not _is_audio_modified():
        # Audio is unmodified — try to stream copy
        source_codec = _detect_source_audio_codec(es_audio)

        if safe_codecs is None or source_codec in safe_codecs:
            # Source codec is compatible (or container has no restrictions) — copy
            return ['-c:a', 'copy']
        else:
            # Source codec isn't container-safe — must re-encode
            codec_name = source_codec or 'unknown'
            print(f'Note: Re-encoding audio as {container_default.upper()} '
                  f'({codec_name} is not widely supported in {video_format.upper()} containers).')
            return ['-c:a', container_default]
    else:
        # Audio was modified — must re-encode
        if configured_codec is not None:
            # User explicitly set a codec — check container compatibility
            if safe_codecs is not None and configured_codec not in safe_codecs:
                print(f'Warning: {configured_codec} is not widely supported in {video_format.upper()} '
                      f'containers. Using {container_default} instead.')
                return ['-c:a', container_default]
            return ['-c:a', configured_codec]
        else:
            # Auto — use container default
            return ['-c:a', container_default]


def write_audio(es_audio: es.audio.Audio, output_path: str = None,
                audio_format: str = None, overwrite: bool = None) -> dict | None:
    """Export processed audio to a file via FFmpeg.

    Encodes the audio from ``es_audio.file`` (which may be a temp WAV from the
    processing chain) to the configured codec and format. After encoding, generates
    a visualization image and embeds it as album art along with metadata tags.

    When ``audio.export.codec`` and ``audio.export.format`` are auto (None), the
    codec and format are inferred from the output file extension (if the output path
    specifies a file), or from the source file's codec and format.

    :param es_audio: Audio instance (with processing already applied).
    :param output_path: Output directory or file path.
    :param audio_format: Output format override (default from config).
    :param overwrite: Overwrite behavior override.
    :return dict: ``{file, encoding_time, file_size}`` on success, ``None`` on failure.
    """
    output_path = output_path if output_path is not None else es.cfg['files.output.path']

    # When the output path points to a specific file, use its extension for codec/format
    # resolution before computing the final output file path
    output_file_hint = None
    if output_path and not os.path.isdir(output_path):
        _, ext = os.path.splitext(output_path)
        if ext:
            output_file_hint = output_path

    codec = _resolve_audio_codec(es_audio, output_file=output_file_hint)
    audio_format = audio_format if audio_format is not None else _resolve_audio_format(es_audio, codec)

    output_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.source_file,
        file_format=audio_format
    )

    try:
        output_valid = es.utils.validate_output_file(output_file=output_file, overwrite=overwrite)
        if not output_valid:
            return None
    except Exception as e:
        print(e)
        return None

    # Build FFmpeg command
    sample_rate = es.cfg['audio.export.sample-rate']
    ffmpeg_extra_args = _resolve_audio_extra_args(codec)

    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', es_audio.file,
        '-c:a', codec,
    ]

    if sample_rate is not None:
        cmd += ['-ar', str(sample_rate)]

    cmd += ffmpeg_extra_args
    cmd.append(output_file)

    with es.utils.Spinner(f'Encoding audio ({codec})... '):
        encoding_start = time.time()
        subprocess.run(cmd, check=True)
        encoding_time = time.time() - encoding_start

    # Generate visualization image and write metadata to the encoded file
    try:
        # Generate album art from the processed audio (with triphase if configured for image export)
        viz_audio = es_audio
        if es.cfg['visualization.image.export.triphase'] and es_audio.channels == 2:
            viz_audio = es_audio.with_triphase()

        image_file = write_image(es_audio=viz_audio, output_path=es.utils.get_temp_file_path())
        es.utils.add_temp_file(image_file)

        output_metadata = es.metadata.Metadata(file=output_file)
        output_metadata.set_metadata(es_audio.metadata.get_metadata())

        image_data = open(image_file, 'rb').read()
        output_metadata.set_tag('image', image_data)

        with es.utils.Spinner(f'Writing metadata... '):
            output_metadata.save()
    except Exception as e:
        print(f'Warning: Failed to write metadata to audio file: {e}')

    es.utils.delete_temp_files()

    file_size = os.path.getsize(output_file)

    print(f'Saved file "{output_file}" ({file_size} bytes).')

    return {
        'file': output_file,
        'encoding_time': encoding_time,
        'file_size': file_size,
    }


def write_image(es_audio: es.audio.Audio, output_path: str = None, image_format: str = None,
                width: int = None, height: int = None, overwrite: bool = None,
                triphase: bool = None) -> str | None:
    output_path = output_path if output_path is not None else es.cfg['files.output.path']
    image_format = es.cfg['visualization.image.export.format'] if image_format is None else image_format

    image_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.source_file,
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
            _draw_ss_badge_on_image(
                image_file, width, height,
                time_enabled=es.cfg['visualization.image.export.time.enabled'],
                time_position=es.cfg['visualization.image.export.time.position'])

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
    video_format = video_format if video_format is not None else es.cfg['video.export.format']
    segment_start = segment_start if segment_start is not None else 1

    # Determine the number of frames per segment
    frames_per_segment = es.cfg['video.export.segment-length'] * es.cfg['video.export.fps']

    video_file = es.utils.get_output_file(
        output_path=output_path,
        input_file_name=es_audio.source_file,
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
    seconds_total = float(es.cfg['video.export.video-length-max']) if \
        es.cfg['video.export.video-length-max'] is not None else es_audio.length

    # Set the total number of frames
    frames_total = math.floor(seconds_total * es.cfg['video.export.fps'])

    # Set preview parameters
    preview_seconds = (
        min(es.cfg['video.export.preview.length'], seconds_total) if es.cfg['video.export.preview.enabled']
        else 0
    )
    preview_frames = preview_seconds * es.cfg['video.export.fps']
    fade_seconds = min(es.cfg['video.export.preview.fade-length'], seconds_total)

    # If a starting frame is specified rather than a segment, determine the starting segment based upon the frame
    if frame_start is not None:
        segment_start = max(math.floor((frame_start - preview_frames) / frames_per_segment) + 1, 1)

    # Generate list of video segments
    video_segment_ids = []

    if es.cfg['video.export.preview.enabled']:
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
    if es.cfg['video.export.keyframe-interval'] is not None:
        ffmpeg_extra_args.extend([
            '-g',
            str(es.cfg['video.export.keyframe-interval'] * es.cfg['video.export.fps'])
        ])

    ffmpeg_extra_args += _build_ffmpeg_extra_args('video.export.ffmpeg-extra-args.')

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

        segment_length = frame_count * es.cfg["video.export.fps"]

        # The last frame of the segment must be a keyframe to allow concatenation without re-encoding
        ffmpeg_keyframe_args = [
            '-force_key_frames',
            f'expr:gte(t,{segment_length - 1 / es.cfg["video.export.fps"]})'
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
            '-r', str(es.cfg['video.export.fps']),
            '-i', 'pipe:0',
            '-c:v', es.cfg['video.export.codec'],
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
                '-r', str(es.cfg['video.export.fps']),
                '-c:v', es.cfg['video.export.codec'],
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
        es.cfg['video.export.codec'] if segments_total > 1 and es.cfg['video.export.reencode-segments']
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

    # Determine audio codec — stream copy when possible, re-encode when audio has been modified
    # or when the source codec isn't compatible with the video container
    audio_codec_args = _resolve_video_audio_codec(es_audio) + ['-strict', '-1']

    ffmpeg_command = [
        'ffmpeg',
        '-f', 'concat', '-safe', '0',  # "-safe 0" allows for absolute paths to files
        '-i', video_segment_list_file,
        '-i', es_audio.file,
        '-c:v', concat_video_codec,
        *audio_codec_args,
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
