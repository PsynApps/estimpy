#!/usr/bin/env python3
"""Generate test2.wav by selecting 24 diverse 5-second segments from test MP3s.

Segments are chosen via greedy farthest-point selection in a 5-dimensional
feature space (RMS, spectral centroid, spectral bandwidth, envelope modulation,
spectral flatness) to maximize audio diversity. Results are sorted from simple
to complex.
"""

import os
import sys

import numpy as np
from pydub import AudioSegment

INPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'tests', 'input')
OUTPUT_PATH = os.path.join(INPUT_DIR, 'test2.wav')

SEGMENT_DURATION_MS = 5000
SEGMENT_STRIDE_MS = 10000
SKIP_BOOKEND_MS = 10000
TARGET_RATE = 44100
NUM_SEGMENTS = 24
CROSSFADE_MS = 50
MIN_PULSED_SEGMENTS = 3


def load_mp3_files():
    """Load all MP3 files from the input directory."""
    files = []
    for name in sorted(os.listdir(INPUT_DIR)):
        if not name.lower().endswith('.mp3'):
            continue
        path = os.path.join(INPUT_DIR, name)
        print(f"Loading {name}...")
        seg = AudioSegment.from_mp3(path)
        seg = seg.set_frame_rate(TARGET_RATE).set_channels(2)
        files.append((name, seg))
    return files


def extract_candidates(files):
    """Extract 5-second candidate segments with computed feature vectors."""
    candidates = []

    for name, audio in files:
        duration_ms = len(audio)
        start = SKIP_BOOKEND_MS
        end = duration_ms - SKIP_BOOKEND_MS - SEGMENT_DURATION_MS

        if end <= start:
            print(f"  Skipping {name}: too short ({duration_ms / 1000:.1f}s)")
            continue

        offset = start
        while offset <= end:
            segment = audio[offset:offset + SEGMENT_DURATION_MS]
            features = compute_features(segment)

            if features is not None:
                candidates.append({
                    'file': name,
                    'start_ms': offset,
                    'segment': segment,
                    'features': features,
                })

            offset += SEGMENT_STRIDE_MS

    print(f"\n{len(candidates)} candidate segments extracted")
    return candidates


def compute_features(segment):
    """Compute a 5-element feature vector for an audio segment.

    Returns None if the segment is silent or spectrally unstable.
    """
    samples = np.array(segment.get_array_of_samples(), dtype=np.float32)
    # Interleaved stereo → mono by averaging channels
    if segment.channels == 2:
        samples = (samples[0::2] + samples[1::2]) / 2.0
    samples /= 32768.0  # Normalize to [-1, 1]

    # Reject near-silent segments
    rms = np.sqrt(np.mean(samples ** 2))
    if rms < 0.005:
        return None

    # Spectral features from full-segment FFT
    n = len(samples)
    fft = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(n, d=1.0 / TARGET_RATE)

    # Avoid DC
    fft = fft[1:]
    freqs = freqs[1:]

    power = fft ** 2
    total_power = power.sum()
    if total_power == 0:
        return None

    weights = power / total_power
    spectral_centroid = np.sum(freqs * weights)
    spectral_bandwidth = np.sqrt(np.sum(((freqs - spectral_centroid) ** 2) * weights))

    # Spectral flatness: geometric mean / arithmetic mean of power spectrum
    log_power = np.log(power + 1e-20)
    geometric_mean = np.exp(np.mean(log_power))
    arithmetic_mean = np.mean(power)
    spectral_flatness = geometric_mean / (arithmetic_mean + 1e-20)

    # Envelope modulation: coefficient of variation of 50ms RMS windows
    window_samples = int(0.05 * TARGET_RATE)
    n_windows = len(samples) // window_samples
    if n_windows < 2:
        return None
    windowed = samples[:n_windows * window_samples].reshape(n_windows, window_samples)
    window_rms = np.sqrt(np.mean(windowed ** 2, axis=1))
    mean_rms = window_rms.mean()
    if mean_rms < 1e-6:
        return None
    envelope_modulation = window_rms.std() / mean_rms

    # Stability check: spectral centroid variance across 0.5s sub-windows
    sub_window_samples = int(0.5 * TARGET_RATE)
    n_sub = len(samples) // sub_window_samples
    if n_sub >= 2:
        sub_centroids = []
        for i in range(n_sub):
            chunk = samples[i * sub_window_samples:(i + 1) * sub_window_samples]
            sub_fft = np.abs(np.fft.rfft(chunk))
            sub_freqs = np.fft.rfftfreq(len(chunk), d=1.0 / TARGET_RATE)
            sub_fft = sub_fft[1:]
            sub_freqs = sub_freqs[1:]
            sub_power = sub_fft ** 2
            sub_total = sub_power.sum()
            if sub_total > 0:
                sub_centroids.append(np.sum(sub_freqs * sub_power / sub_total))
        if len(sub_centroids) >= 2:
            centroid_cv = np.std(sub_centroids) / (np.mean(sub_centroids) + 1e-10)
            if centroid_cv > 0.5:
                return None

    return np.array([rms, spectral_centroid, spectral_bandwidth, envelope_modulation, spectral_flatness])


def normalize_features(candidates):
    """Normalize all feature vectors to [0, 1] range."""
    features = np.array([c['features'] for c in candidates])
    mins = features.min(axis=0)
    maxs = features.max(axis=0)
    ranges = maxs - mins
    ranges[ranges == 0] = 1.0  # Avoid division by zero

    for c in candidates:
        c['features_norm'] = (c['features'] - mins) / ranges


def greedy_farthest_point_selection(candidates, n):
    """Select n segments via greedy farthest-point sampling in feature space."""
    features = np.array([c['features_norm'] for c in candidates])
    centroid = features.mean(axis=0)

    # Start with the segment closest to the centroid
    distances_to_centroid = np.linalg.norm(features - centroid, axis=1)
    first_idx = np.argmin(distances_to_centroid)

    selected_indices = [first_idx]
    # Track min distance from each candidate to any selected point
    min_distances = np.linalg.norm(features - features[first_idx], axis=1)

    for _ in range(n - 1):
        # Mask already-selected
        min_distances[selected_indices[-1]] = -1
        # Pick the candidate farthest from all selected
        next_idx = np.argmax(min_distances)
        selected_indices.append(next_idx)
        # Update min distances
        new_distances = np.linalg.norm(features - features[next_idx], axis=1)
        min_distances = np.minimum(min_distances, new_distances)

    return selected_indices


def ensure_pulse_diversity(candidates, selected_indices):
    """Ensure at least MIN_PULSED_SEGMENTS segments have high envelope modulation."""
    # Envelope modulation is feature index 3
    modulation_threshold = np.percentile(
        [c['features'][3] for c in candidates], 75
    )

    pulsed_in_selection = [
        i for i in selected_indices
        if candidates[i]['features'][3] >= modulation_threshold
    ]

    if len(pulsed_in_selection) >= MIN_PULSED_SEGMENTS:
        return selected_indices

    # Find candidates with highest modulation not already selected
    selected_set = set(selected_indices)
    unselected_pulsed = [
        (i, candidates[i]['features'][3])
        for i in range(len(candidates))
        if i not in selected_set and candidates[i]['features'][3] >= modulation_threshold
    ]
    unselected_pulsed.sort(key=lambda x: x[1], reverse=True)

    # Find selected segments with lowest modulation to swap out
    selected_by_modulation = sorted(
        selected_indices,
        key=lambda i: candidates[i]['features'][3]
    )

    needed = MIN_PULSED_SEGMENTS - len(pulsed_in_selection)
    for swap_count in range(min(needed, len(unselected_pulsed))):
        # Swap out lowest-modulation selected for highest-modulation unselected
        out_idx = selected_by_modulation[swap_count]
        in_idx = unselected_pulsed[swap_count][0]
        pos = selected_indices.index(out_idx)
        selected_indices[pos] = in_idx

    return selected_indices


def sort_by_complexity(candidates, selected_indices):
    """Sort selected segments by complexity (simple → complex)."""
    def complexity_score(idx):
        f = candidates[idx]['features']
        # Weighted: spectral_bandwidth (2) + envelope_modulation (3) + spectral_flatness (4)
        norm = candidates[idx]['features_norm']
        return 0.4 * norm[2] + 0.4 * norm[3] + 0.2 * norm[4]

    return sorted(selected_indices, key=complexity_score)


def concatenate_segments(candidates, selected_indices):
    """Concatenate selected segments with crossfades and export."""
    result = candidates[selected_indices[0]]['segment']

    for idx in selected_indices[1:]:
        result = result.append(candidates[idx]['segment'], crossfade=CROSSFADE_MS)

    result.export(OUTPUT_PATH, format='wav', parameters=['-acodec', 'pcm_s16le'])
    return result


def print_manifest(candidates, selected_indices):
    """Print details of selected segments for manual verification."""
    feature_names = ['RMS', 'Centroid(Hz)', 'Bandwidth(Hz)', 'EnvMod(CV)', 'Flatness']

    print(f"\n{'#':>3}  {'File':<55} {'Start':>6}  ", end='')
    for name in feature_names:
        print(f'{name:>14}', end='')
    print()
    print('-' * 145)

    for rank, idx in enumerate(selected_indices, 1):
        c = candidates[idx]
        f = c['features']
        print(f"{rank:3d}  {c['file']:<55} {c['start_ms'] / 1000:5.1f}s  ", end='')
        print(f"{f[0]:14.4f}{f[1]:14.1f}{f[2]:14.1f}{f[3]:14.4f}{f[4]:14.6f}")

    print()


def main():
    print("=== Generating test2.wav ===\n")

    files = load_mp3_files()
    if not files:
        print("ERROR: No MP3 files found in", INPUT_DIR)
        sys.exit(1)

    candidates = extract_candidates(files)
    if len(candidates) < NUM_SEGMENTS:
        print(f"ERROR: Only {len(candidates)} candidates, need {NUM_SEGMENTS}")
        sys.exit(1)

    normalize_features(candidates)

    selected = greedy_farthest_point_selection(candidates, NUM_SEGMENTS)
    selected = ensure_pulse_diversity(candidates, selected)
    selected = sort_by_complexity(candidates, selected)

    print_manifest(candidates, selected)

    result = concatenate_segments(candidates, selected)
    duration_s = len(result) / 1000.0
    print(f"Exported {OUTPUT_PATH}")
    print(f"Duration: {duration_s:.2f}s ({duration_s / 60:.1f} min)")
    print(f"Segments: {NUM_SEGMENTS}, Crossfade: {CROSSFADE_MS}ms")


if __name__ == '__main__':
    main()
