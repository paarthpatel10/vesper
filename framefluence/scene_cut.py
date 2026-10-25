"""
Framefluence - Automatic clip cutting.
Uses PySceneDetect to find shot boundaries and picks a 20-60s segment that starts
and ends on a clean cut, so reels never open or close mid-shot.
"""

import subprocess


def detect_scenes(video_path):
    """Returns [(start_sec, end_sec), ...] for each shot. Requires `scenedetect[opencv]`."""
    from scenedetect import ContentDetector, detect

    scenes = detect(video_path, ContentDetector())
    return [(s.get_seconds(), e.get_seconds()) for s, e in scenes]


def probe_duration(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def choose_segment(scenes, total_duration, min_len=20.0, max_len=60.0):
    """
    Picks (start, end) covering whole consecutive shots, between min_len and max_len long.
    Prefers the longest such run (more story) and, on ties, the earliest. Falls back to the
    first max_len seconds when no run of shots fits (e.g. one very long take).
    """
    if total_duration <= max_len:
        return 0.0, total_duration
    if not scenes:
        return 0.0, max_len

    best = None
    for i in range(len(scenes)):
        start = scenes[i][0]
        for j in range(i, len(scenes)):
            length = scenes[j][1] - start
            if length > max_len:
                break
            if length >= min_len and (best is None or length > best[1] - best[0]):
                best = (start, scenes[j][1])
    return best or (0.0, max_len)


def audio_energy(video_path, frame_sec=0.25):
    """Returns per-frame RMS loudness (list of floats) of the mono 16kHz audio. Requires numpy."""
    import numpy as np

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    n = int(16000 * frame_sec)
    frames = samples[: len(samples) // n * n].reshape(-1, n)
    return np.sqrt((frames ** 2).mean(axis=1)).tolist()


def speech_breaks(words, shots, min_gap=1.0, snap=0.6):
    """
    Natural cut points: pauses between words (>= min_gap) that land on a shot cut, so a clip never
    starts or ends mid-sentence or mid-shot. Returns [(time, gap_length), ...].
    """
    cuts = [s for s, _ in shots]
    breaks = []
    for prev, nxt in zip(words, words[1:]):
        gap = nxt["start"] - prev["end"]
        if gap < min_gap:
            continue
        inside = [c for c in cuts if prev["end"] - snap <= c <= nxt["start"] + snap]
        if inside:
            breaks.append((inside[-1], gap))
    # The first cut after the final line, so a scene that runs to the end of the source can still close
    after = [c for c in cuts if words and c >= words[-1]["end"] - snap]
    if after:
        breaks.append((after[0], 99.0))
    return breaks


def rank_story_segments(words, shots, energy, total_duration, min_len=60.0, max_len=118.0,
                        frame_sec=0.25, transition_gap=8.0, max_laugh_sec=6.0, top_n=3):
    """
    Ranks complete story beats rather than just a run of shots. Each candidate window runs between
    two natural breaks and is scored on:
      - laughter: audience-track loudness while nobody is speaking (sitcom laugh track = engagement)
      - dialogue density: share of the window with someone talking
      - payoff: a big reaction in the final seconds (the beat lands before the cut)
    Windows containing a long silent gap (theme song / scene transition) are rejected.
    Returns up to top_n non-overlapping [(start, end, score), ...], best first.
    """
    if not words or not energy:
        return []
    speaking = [False] * len(energy)
    for w in words:
        for i in range(int(w["start"] / frame_sec), min(len(energy), int(w["end"] / frame_sec) + 1)):
            speaking[i] = True
    quiet = sorted(energy)[len(energy) // 2]
    laugh = [max(0.0, e - quiet) if not s else 0.0 for e, s in zip(energy, speaking)]
    # Laughs are short bursts between lines; a long loud stretch without speech is music (theme, band)
    run_start = None
    for i in range(len(laugh) + 1):
        talking = i == len(laugh) or speaking[i]
        if not talking and run_start is None:
            run_start = i
        elif talking and run_start is not None:
            if (i - run_start) * frame_sec > max_laugh_sec:
                laugh[run_start:i] = [0.0] * (i - run_start)
            run_start = None
    peak = max(laugh) or 1.0

    breaks = [(0.0, 99.0)] + speech_breaks(words, shots) + [(total_duration, 99.0)]
    word_starts = [w["start"] for w in words]
    candidates = []
    for i, (start, _) in enumerate(breaks):
        for end, _ in breaks[i + 1:]:
            length = end - start
            if length > max_len:
                break
            if length < min_len:
                continue
            inside = [t for t in word_starts if start <= t < end]
            if len(inside) < 10:
                continue
            # A long wordless stretch anywhere (including the edges) means a transition or theme song
            marks = [start] + inside + [end]
            if max(b - a for a, b in zip(marks, marks[1:])) > transition_gap:
                continue
            a, b = int(start / frame_sec), int(end / frame_sec)
            window_laugh = sum(laugh[a:b]) / peak / length
            density = sum(speaking[a:b]) / max(1, b - a)
            payoff = max(laugh[max(a, b - int(6 / frame_sec)):b] or [0.0]) / peak
            candidates.append((start, end, 2.0 * window_laugh + density + 0.8 * payoff))

    picked = []
    for start, end, score in sorted(candidates, key=lambda c: -c[2]):
        if all(end <= s or start >= e for s, e, _ in picked):
            picked.append((start, end, score))
            if len(picked) == top_n:
                break
    return picked


def choose_story_segment(words, shots, energy, total_duration, **kwargs):
    """The single best story beat as (start, end), or None. See rank_story_segments."""
    ranked = rank_story_segments(words, shots, energy, total_duration, top_n=1, **kwargs)
    return ranked[0][:2] if ranked else None


def cut_clip(video_path, start, end, output_path):
    """Re-encodes [start, end) into output_path so timestamps restart at zero for later steps."""
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", video_path, "-t", f"{end - start:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path
