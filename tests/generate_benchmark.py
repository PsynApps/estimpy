#!/usr/bin/env python3
"""Generate the benchmark.mp3 fixture from source audio files.

Analyzes all audio files in tests/input/benchmark/, identifies diverse segments
based on amplitude and frequency characteristics, and concatenates them into a
benchmark file.

Usage:
    python tests/generate_benchmark.py
    python tests/generate_benchmark.py --output-length 120 --segment-length 10

Requires source audio files in tests/input/benchmark/ (not included in the
repository — add your own estim audio files to this directory).
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np
import pydub


# --- Constants ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(SCRIPT_DIR, 'input', 'benchmark')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'input', 'benchmark.mp3')

SUB_WINDOW_COUNT = 10        # sub-windows per segment for feature analysis
FADE_DURATION = 0.02         # seconds of fade-in/fade-out per segment
SILENCE_THRESHOLD = 0.01     # minimum mean RMS to consider a segment
TRANSITION_RATIO = 2.0       # max ratio between half-means before rejecting as transition
TRANSITION_CENTROID_HZ = 500 # max spectral centroid shift between halves

FEATURE_KEYS = ['mean_rms', 'mean_centroid', 'mean_bandwidth', 'amp_cv']


def load_audio(file):
    """Load an audio file and return (samples, sample_rate, channels).

    Returns samples as float32 array shaped (channels, samples) normalized to [-1, 1].
    """
    audio_segment = pydub.AudioSegment.from_file(file)
    sample_rate = audio_segment.frame_rate
    bit_depth = 8 * audio_segment.sample_width
    channels = audio_segment.channels

    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
    samples = samples.reshape((channels, -1), order='F')
    samples /= 2 ** (bit_depth - 1)

    return samples, sample_rate, channels


def compute_rms(samples):
    """Compute RMS amplitude of a 1D or 2D array (across last axis)."""
    return np.sqrt(np.mean(samples ** 2, axis=-1))


def compute_spectral_features(samples, sample_rate):
    """Compute spectral centroid and bandwidth from a signal.

    Returns (centroid_hz, bandwidth_hz).
    """
    # Mix to mono if stereo
    if samples.ndim > 1:
        mono = np.mean(samples, axis=0)
    else:
        mono = samples

    # Compute magnitude spectrum
    n = len(mono)
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    # Avoid division by zero
    total_energy = np.sum(spectrum)
    if total_energy < 1e-10:
        return 0.0, 0.0

    centroid = np.sum(freqs * spectrum) / total_energy
    bandwidth = np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / total_energy)

    return float(centroid), float(bandwidth)


def analyze_segment(samples, sample_rate):
    """Analyze a segment and return its feature dict, or None if rejected.

    Computes features on sub-windows, filters transitions, and returns
    aggregate features for diversity selection.
    """
    total_samples = samples.shape[-1]
    sub_window_size = total_samples // SUB_WINDOW_COUNT

    sub_rms = []
    sub_centroids = []
    sub_bandwidths = []

    for i in range(SUB_WINDOW_COUNT):
        start = i * sub_window_size
        end = start + sub_window_size
        chunk = samples[:, start:end] if samples.ndim > 1 else samples[start:end]

        rms = float(compute_rms(chunk.flatten()))
        centroid, bandwidth = compute_spectral_features(chunk, sample_rate)

        sub_rms.append(rms)
        sub_centroids.append(centroid)
        sub_bandwidths.append(bandwidth)

    sub_rms = np.array(sub_rms)
    sub_centroids = np.array(sub_centroids)

    mean_rms = float(np.mean(sub_rms))
    mean_centroid = float(np.mean(sub_centroids))
    mean_bandwidth = float(np.mean(sub_bandwidths))

    # Reject silence
    if mean_rms < SILENCE_THRESHOLD:
        return None, 'silence'

    # Amplitude modulation depth (CV of sub-window RMS)
    amp_cv = float(np.std(sub_rms) / mean_rms) if mean_rms > 0 else 0.0

    # Transition detection: compare first half vs second half
    half = SUB_WINDOW_COUNT // 2
    first_rms = float(np.mean(sub_rms[:half]))
    second_rms = float(np.mean(sub_rms[half:]))
    first_centroid = float(np.mean(sub_centroids[:half]))
    second_centroid = float(np.mean(sub_centroids[half:]))

    # Reject if RMS ratio between halves is too large
    if first_rms > 0 and second_rms > 0:
        rms_ratio = max(first_rms, second_rms) / min(first_rms, second_rms)
        if rms_ratio > TRANSITION_RATIO:
            return None, 'transition_rms'

    # Reject if spectral centroid shifts too much between halves
    if abs(first_centroid - second_centroid) > TRANSITION_CENTROID_HZ:
        return None, 'transition_centroid'

    return {
        'mean_rms': mean_rms,
        'mean_centroid': mean_centroid,
        'mean_bandwidth': mean_bandwidth,
        'amp_cv': amp_cv,
    }, None


def build_feature_matrix(candidates):
    """Build a normalized feature matrix from a list of candidates.

    Returns (normalized_matrix, mins, ranges) where normalized_matrix has
    values in [0, 1] for each feature dimension.
    """
    features = np.array([[c['features'][k] for k in FEATURE_KEYS] for c in candidates])
    mins = features.min(axis=0)
    ranges = features.max(axis=0) - mins
    ranges[ranges == 0] = 1.0
    normalized = (features - mins) / ranges
    return normalized, mins, ranges


def farthest_first_select(normalized, count, excluded=None):
    """Select indices using greedy farthest-first traversal.

    Args:
        normalized: (N, D) normalized feature matrix.
        count: Number of indices to select.
        excluded: Set of indices to exclude from selection (already selected).

    Returns list of selected indices.
    """
    if excluded is None:
        excluded = set()

    available = set(range(len(normalized))) - excluded
    if not available or count <= 0:
        return []

    # Start with the candidate closest to the centroid of available candidates
    available_features = np.array([normalized[i] for i in sorted(available)])
    available_indices = sorted(available)
    centroid = available_features.mean(axis=0)
    distances_to_centroid = np.linalg.norm(available_features - centroid, axis=1)
    selected = [available_indices[int(np.argmin(distances_to_centroid))]]

    for _ in range(count - 1):
        # For each candidate, compute min distance to any selected candidate
        min_distances = np.full(len(normalized), -1.0)
        for i in available - set(selected):
            min_dist = min(np.linalg.norm(normalized[i] - normalized[s]) for s in selected)
            min_distances[i] = min_dist

        next_idx = int(np.argmax(min_distances))
        if min_distances[next_idx] <= 0:
            break  # No more available candidates
        selected.append(next_idx)

    return selected


def select_segments(candidates, segment_count):
    """Select segments ensuring file representation and maximizing diversity.

    Strategy:
    1. Select one segment per file (most diverse representative from each).
       If more files than slots, use one-per-file constrained diversity selection.
    2. Fill remaining slots with farthest-first traversal across all candidates.
    3. If total unique segments < segment_count, repeat selected segments cyclically.
    """
    # Group candidates by file
    file_candidates = {}
    for i, c in enumerate(candidates):
        file_candidates.setdefault(c['file'], []).append(i)

    num_files = len(file_candidates)
    normalized, _, _ = build_feature_matrix(candidates)

    if num_files >= segment_count:
        # More files than slots: pick one per file, maximize diversity across files
        # First, find the best representative from each file (farthest from global centroid)
        centroid = normalized.mean(axis=0)
        file_reps = {}
        for file, indices in file_candidates.items():
            distances = [np.linalg.norm(normalized[i] - centroid) for i in indices]
            file_reps[file] = indices[int(np.argmax(distances))]

        # Now select `segment_count` from these representatives using farthest-first
        rep_indices = list(file_reps.values())
        rep_normalized = normalized[rep_indices]

        # Farthest-first on the representatives
        rep_centroid = rep_normalized.mean(axis=0)
        distances_to_centroid = np.linalg.norm(rep_normalized - rep_centroid, axis=1)
        selected_rep = [int(np.argmin(distances_to_centroid))]

        for _ in range(segment_count - 1):
            min_distances = np.full(len(rep_indices), -1.0)
            for j in range(len(rep_indices)):
                if j not in selected_rep:
                    min_dist = min(np.linalg.norm(rep_normalized[j] - rep_normalized[s])
                                   for s in selected_rep)
                    min_distances[j] = min_dist
            next_idx = int(np.argmax(min_distances))
            if min_distances[next_idx] <= 0:
                break
            selected_rep.append(next_idx)

        return [rep_indices[j] for j in selected_rep]

    # Fewer files than slots: guarantee one per file, then fill with diversity
    # Round 1: Pick one representative per file (farthest from global centroid)
    selected = []
    centroid = normalized.mean(axis=0)
    for file, indices in file_candidates.items():
        distances = [np.linalg.norm(normalized[i] - centroid) for i in indices]
        selected.append(indices[int(np.argmax(distances))])

    remaining_slots = segment_count - len(selected)

    if remaining_slots > 0:
        # Round 2: Fill remaining slots with farthest-first from all candidates
        additional = farthest_first_select(normalized, remaining_slots, excluded=set(selected))
        selected.extend(additional)

    # Round 3: If still not enough unique segments, repeat cyclically
    if len(selected) < segment_count:
        base = list(selected)
        while len(selected) < segment_count:
            selected.append(base[len(selected) % len(base)])

    return selected


def encode_single_file(source_file, output_length, output_file):
    """Encode a single source file directly when it's the only source and short enough."""
    samples, sample_rate, channels = load_audio(source_file)
    duration = samples.shape[-1] / sample_rate

    if duration > output_length:
        return False  # File is too long, use segment approach

    print(f'Single file ({duration:.1f}s) fits within output length ({output_length:.0f}s), encoding directly.')
    encode_to_mp3(samples, sample_rate, output_file)
    return True


def encode_to_mp3(samples, sample_rate, output_file):
    """Encode a float32 samples array to an MP3 file."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        import scipy.io.wavfile

        int16_data = np.clip(samples * 32767, -32768, 32767).astype(np.int16)
        interleaved = int16_data.T  # (samples, channels)
        scipy.io.wavfile.write(tmp_wav, sample_rate, interleaved)

        print('Encoding to MP3...')
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', tmp_wav,
            '-codec:a', 'libmp3lame',
            '-q:a', '0',
            output_file
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(tmp_wav)

    file_size = os.path.getsize(output_file)
    print(f'Wrote {output_file} ({file_size / 1024:.0f} KB)')


def format_time(seconds):
    """Format seconds as M:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f'{m}:{s:02d}'


def main():
    parser = argparse.ArgumentParser(
        description='Generate benchmark.mp3 from source audio files in tests/input/benchmark/.')
    parser.add_argument('--output-length', type=float, default=60.0,
        help='Total output length in seconds (default: 60).')
    parser.add_argument('--segment-length', type=float, default=5.0,
        help='Length of each segment in seconds (default: 5).')
    parser.add_argument('--output', type=str, default=OUTPUT_FILE,
        help=f'Output MP3 file path (default: {OUTPUT_FILE}).')
    args = parser.parse_args()

    output_length = args.output_length
    segment_length = args.segment_length
    output_file = args.output

    # Check for existing output file
    if os.path.exists(output_file):
        response = input(f'{output_file} already exists. Overwrite? [y/N] ')
        if response.lower() != 'y':
            print('Aborted.')
            sys.exit(0)

    if segment_length > output_length:
        print(f'Error: Segment length ({segment_length}s) exceeds output length ({output_length}s).')
        sys.exit(1)

    segment_count = int(output_length / segment_length)
    # Last segment may be truncated if output_length isn't evenly divisible
    last_segment_length = output_length - (segment_count - 1) * segment_length
    if last_segment_length > segment_length:
        segment_count += 1
        last_segment_length = output_length - (segment_count - 1) * segment_length

    # Discover source files
    source_files = sorted(
        f for f in glob.glob(os.path.join(SOURCE_DIR, '*'))
        if os.path.isfile(f)
    )

    if not source_files:
        print(f'Error: No audio files found in {SOURCE_DIR}')
        print('Add estim audio files to this directory and re-run.')
        sys.exit(1)

    print(f'Source directory: {SOURCE_DIR}')
    print(f'Found {len(source_files)} source file(s)')
    print(f'Output: {output_length:.0f}s total, {segment_length:.0f}s segments, {segment_count} segments')
    print()

    # Single file special case
    if len(source_files) == 1:
        if encode_single_file(source_files[0], output_length, output_file):
            return
        # File is longer than output length — fall through to segment approach
        print('File exceeds output length, using segment selection.')
        print()

    # Phase 1 & 2: Extract and analyze candidate segments
    candidates = []
    reject_counts = {'silence': 0, 'transition_rms': 0, 'transition_centroid': 0}
    files_with_candidates = set()

    for file in source_files:
        filename = os.path.basename(file)
        print(f'Analyzing: {filename}... ', end='', flush=True)

        try:
            samples, sample_rate, channels = load_audio(file)
        except Exception as e:
            print(f'FAILED ({e})')
            continue

        duration = samples.shape[-1] / sample_rate
        segment_samples = int(segment_length * sample_rate)
        num_candidates = int(duration // segment_length)

        file_accepted = 0
        for i in range(num_candidates):
            start_sample = i * segment_samples
            end_sample = start_sample + segment_samples
            segment = samples[:, start_sample:end_sample]

            features, reject_reason = analyze_segment(segment, sample_rate)

            if features is None:
                reject_counts[reject_reason] += 1
                continue

            candidates.append({
                'file': file,
                'filename': filename,
                'start_sample': start_sample,
                'start_time': i * segment_length,
                'sample_rate': sample_rate,
                'channels': channels,
                'features': features,
            })
            file_accepted += 1

        if file_accepted > 0:
            files_with_candidates.add(file)
        else:
            print(f'WARNING — no valid segments', end='')

        print(f' ({file_accepted}/{num_candidates} candidates)')

    # Report files with no valid candidates
    files_without = set(source_files) - files_with_candidates
    for file in files_without:
        if file not in [f for f in source_files if os.path.basename(file) in
                        [c['filename'] for c in candidates]]:
            pass  # Already warned during analysis

    total_rejected = sum(reject_counts.values())
    print()
    print(f'Total candidates: {len(candidates)} accepted, {total_rejected} rejected '
          f'(silence: {reject_counts["silence"]}, '
          f'transition_rms: {reject_counts["transition_rms"]}, '
          f'transition_centroid: {reject_counts["transition_centroid"]})')

    if len(candidates) == 0:
        print('Error: No valid candidates found across all files.')
        sys.exit(1)

    # Phase 3: Select diverse segments
    selected_indices = select_segments(candidates, segment_count)
    selected = [candidates[i] for i in selected_indices]

    # Report selection
    unique_files = len(set(s['file'] for s in selected))
    print()
    print(f'Selected {len(selected)} segments from {unique_files} file(s):')
    for i, seg in enumerate(selected):
        f = seg['features']
        truncated = ' (truncated)' if i == len(selected) - 1 and last_segment_length < segment_length else ''
        print(f'  {i + 1:2d}. {seg["filename"]:<45s} @ {format_time(seg["start_time"]):>5s}  '
              f'(rms={f["mean_rms"]:.3f}, centroid={f["mean_centroid"]:.0f}Hz, '
              f'bw={f["mean_bandwidth"]:.0f}Hz, cv={f["amp_cv"]:.2f}){truncated}')

    # Phase 4: Assembly
    target_sr = selected[0]['sample_rate']
    target_channels = max(seg['channels'] for seg in selected)

    fade_samples = int(FADE_DURATION * target_sr)
    fade_in = np.linspace(0, 1, fade_samples, dtype=np.float32)
    fade_out = np.linspace(1, 0, fade_samples, dtype=np.float32)

    full_segment_samples = int(segment_length * target_sr)
    last_segment_samples = int(last_segment_length * target_sr)
    assembled_parts = []

    for i, seg in enumerate(selected):
        # Determine sample count for this segment (last may be truncated)
        is_last = (i == len(selected) - 1)
        seg_samples = last_segment_samples if is_last and last_segment_length < segment_length else full_segment_samples

        # Reload the segment from the source file
        samples, sr, ch = load_audio(seg['file'])

        start = seg['start_sample']
        # Adjust start sample if sample rates differ
        if sr != target_sr:
            start = int(seg['start_time'] * target_sr)
            from scipy.signal import resample
            total_resampled = int(samples.shape[-1] * target_sr / sr)
            samples = resample(samples, total_resampled, axis=-1).astype(np.float32)

        end = start + seg_samples
        # Clamp to actual length
        end = min(end, samples.shape[-1])
        segment_audio = samples[:, start:end]

        # Handle channel mismatch: duplicate mono to stereo if needed
        if segment_audio.shape[0] < target_channels:
            segment_audio = np.repeat(segment_audio, target_channels, axis=0)

        # Apply fade-in and fade-out
        actual_fade = min(fade_samples, segment_audio.shape[-1])
        segment_audio[:, :actual_fade] *= fade_in[:actual_fade]
        segment_audio[:, -actual_fade:] *= fade_out[-actual_fade:]

        assembled_parts.append(segment_audio)

    assembled = np.concatenate(assembled_parts, axis=-1)

    print()
    print(f'Assembling {len(selected)} segments ({assembled.shape[-1] / target_sr:.1f}s, '
          f'{target_channels}ch, {target_sr}Hz)...')

    encode_to_mp3(assembled, target_sr, output_file)


if __name__ == '__main__':
    main()
