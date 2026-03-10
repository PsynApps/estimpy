#!/usr/bin/env python3
"""Generate the benchmark.mp3 fixture from source audio files.

Analyzes all audio files in tests/input/benchmark/, identifies 12 diverse
5-second segments based on amplitude and frequency characteristics, and
concatenates them into a 1-minute benchmark file.

Usage:
    python tests/generate_benchmark.py

Requires source audio files in tests/input/benchmark/ (not included in the
repository — add your own estim audio files to this directory).
"""

import glob
import os
import subprocess
import sys
import tempfile

import numpy as np
import pydub


# --- Configuration ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(SCRIPT_DIR, 'input', 'benchmark')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'input', 'benchmark.mp3')

SEGMENT_DURATION = 5.0       # seconds per segment
SEGMENT_COUNT = 12           # number of segments to select
SUB_WINDOW_COUNT = 10        # sub-windows per segment for feature analysis
FADE_DURATION = 0.02         # seconds of fade-in/fade-out per segment
SILENCE_THRESHOLD = 0.01     # minimum mean RMS to consider a segment
TRANSITION_RATIO = 2.0       # max ratio between half-means before rejecting as transition
TRANSITION_CENTROID_HZ = 500 # max spectral centroid shift between halves


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
    """Compute spectral centroid and bandwidth from a mono signal.

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

    # Spectral centroid: weighted mean of frequencies
    centroid = np.sum(freqs * spectrum) / total_energy

    # Spectral bandwidth: weighted std of frequencies
    bandwidth = np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / total_energy)

    return float(centroid), float(bandwidth)


def analyze_segment(samples, sample_rate):
    """Analyze a 5-second segment and return its feature dict, or None if rejected.

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
    sub_bandwidths = np.array(sub_bandwidths)

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


def select_diverse_segments(candidates, count):
    """Select `count` segments that maximize diversity in feature space.

    Uses greedy farthest-first traversal in normalized feature space.
    """
    if len(candidates) <= count:
        return list(range(len(candidates)))

    # Build feature matrix and normalize to [0, 1]
    feature_keys = ['mean_rms', 'mean_centroid', 'mean_bandwidth', 'amp_cv']
    features = np.array([[c['features'][k] for k in feature_keys] for c in candidates])

    mins = features.min(axis=0)
    maxs = features.max(axis=0)
    ranges = maxs - mins
    # Avoid division by zero for constant features
    ranges[ranges == 0] = 1.0
    normalized = (features - mins) / ranges

    # Start with the candidate closest to the centroid
    centroid = normalized.mean(axis=0)
    distances_to_centroid = np.linalg.norm(normalized - centroid, axis=1)
    selected = [int(np.argmin(distances_to_centroid))]

    # Greedy farthest-first
    for _ in range(count - 1):
        # For each candidate, compute min distance to any selected candidate
        min_distances = np.full(len(candidates), np.inf)
        for s in selected:
            dists = np.linalg.norm(normalized - normalized[s], axis=1)
            min_distances = np.minimum(min_distances, dists)

        # Zero out already-selected
        for s in selected:
            min_distances[s] = -1.0

        selected.append(int(np.argmax(min_distances)))

    return selected


def format_time(seconds):
    """Format seconds as M:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f'{m}:{s:02d}'


def main():
    # Discover source files
    source_files = sorted(
        glob.glob(os.path.join(SOURCE_DIR, '*'))
    )
    # Filter to files only (not directories or .gitkeep)
    source_files = [f for f in source_files
                    if os.path.isfile(f) and not f.endswith('.gitkeep')]

    if not source_files:
        print(f'Error: No audio files found in {SOURCE_DIR}')
        print('Add estim audio files to this directory and re-run.')
        sys.exit(1)

    print(f'Source directory: {SOURCE_DIR}')
    print(f'Found {len(source_files)} source files')
    print()

    # Phase 1 & 2: Extract and analyze candidate segments
    candidates = []
    reject_counts = {'silence': 0, 'transition_rms': 0, 'transition_centroid': 0}

    for file in source_files:
        filename = os.path.basename(file)
        print(f'Analyzing: {filename}... ', end='', flush=True)

        try:
            samples, sample_rate, channels = load_audio(file)
        except Exception as e:
            print(f'FAILED ({e})')
            continue

        duration = samples.shape[-1] / sample_rate
        segment_samples = int(SEGMENT_DURATION * sample_rate)
        num_candidates = int(duration // SEGMENT_DURATION)

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
                'start_time': i * SEGMENT_DURATION,
                'sample_rate': sample_rate,
                'channels': channels,
                'features': features,
            })
            file_accepted += 1

        print(f'{file_accepted}/{num_candidates} candidates')

    total_rejected = sum(reject_counts.values())
    print()
    print(f'Total candidates: {len(candidates)} accepted, {total_rejected} rejected '
          f'(silence: {reject_counts["silence"]}, '
          f'transition_rms: {reject_counts["transition_rms"]}, '
          f'transition_centroid: {reject_counts["transition_centroid"]})')

    if len(candidates) < SEGMENT_COUNT:
        print(f'Error: Not enough candidates ({len(candidates)}) to select {SEGMENT_COUNT} segments.')
        sys.exit(1)

    # Phase 4: Select diverse segments
    selected_indices = select_diverse_segments(candidates, SEGMENT_COUNT)
    selected = [candidates[i] for i in selected_indices]

    print()
    print(f'Selected {SEGMENT_COUNT} segments:')
    for i, seg in enumerate(selected):
        f = seg['features']
        print(f'  {i + 1:2d}. {seg["filename"]:<45s} @ {format_time(seg["start_time"]):>5s}  '
              f'(rms={f["mean_rms"]:.3f}, centroid={f["mean_centroid"]:.0f}Hz, '
              f'bw={f["mean_bandwidth"]:.0f}Hz, cv={f["amp_cv"]:.2f})')

    # Phase 5: Assembly
    # Determine output sample rate and channels (use first selected segment's properties)
    # Resample all segments to match if needed
    target_sr = selected[0]['sample_rate']
    target_channels = max(seg['channels'] for seg in selected)

    fade_samples = int(FADE_DURATION * target_sr)
    fade_in = np.linspace(0, 1, fade_samples, dtype=np.float32)
    fade_out = np.linspace(1, 0, fade_samples, dtype=np.float32)

    segment_samples = int(SEGMENT_DURATION * target_sr)
    assembled_parts = []

    for seg in selected:
        # Reload the segment from the source file
        samples, sr, ch = load_audio(seg['file'])

        start = seg['start_sample']
        # Adjust start sample if sample rates differ
        if sr != target_sr:
            start = int(seg['start_time'] * target_sr)
            from scipy.signal import resample
            total_resampled = int(samples.shape[-1] * target_sr / sr)
            samples = resample(samples, total_resampled, axis=-1).astype(np.float32)

        end = start + segment_samples
        segment_audio = samples[:, start:end]

        # Handle channel mismatch: duplicate mono to stereo if needed
        if segment_audio.shape[0] < target_channels:
            segment_audio = np.repeat(segment_audio, target_channels, axis=0)

        # Apply fade-in and fade-out
        segment_audio[:, :fade_samples] *= fade_in
        segment_audio[:, -fade_samples:] *= fade_out

        assembled_parts.append(segment_audio)

    assembled = np.concatenate(assembled_parts, axis=-1)

    # Write to temporary WAV, encode to MP3
    print()
    print(f'Assembling {len(selected)} segments ({assembled.shape[-1] / target_sr:.1f}s, '
          f'{target_channels}ch, {target_sr}Hz)...')

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        # Convert float32 [-1, 1] to int16 for WAV
        int16_data = np.clip(assembled * 32767, -32768, 32767).astype(np.int16)

        # Interleave channels for WAV: shape (samples, channels)
        interleaved = int16_data.T  # (samples, channels)

        import scipy.io.wavfile
        scipy.io.wavfile.write(tmp_wav, target_sr, interleaved)

        print(f'Encoding to MP3...')
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', tmp_wav,
            '-codec:a', 'libmp3lame',
            '-q:a', '0',
            OUTPUT_FILE
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(tmp_wav)

    file_size = os.path.getsize(OUTPUT_FILE)
    print(f'Wrote {OUTPUT_FILE} ({file_size / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
