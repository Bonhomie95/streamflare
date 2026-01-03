import os
import subprocess
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import cv2
import librosa


@dataclass
class Highlight:
    start_sec: float
    duration_sec: float
    score: float


def _extract_audio_wav(video_path: str, wav_path: str) -> None:
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-t",
        "900",  # limit analysis to first 15 mins by default
        wav_path,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed:\n{p.stderr}")


def _audio_energy_scores(
    wav_path: str, window_sec: int, hop_sec: int
) -> Tuple[np.ndarray, int]:
    y, sr_raw = librosa.load(wav_path, sr=22050, mono=True)
    sr = int(sr_raw)
    win = int(window_sec * sr)
    hop = int(hop_sec * sr)

    if len(y) < win:
        return np.array([0.0], dtype=np.float32), sr

    scores = []
    for i in range(0, len(y) - win, hop):
        chunk = y[i : i + win]
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        scores.append(rms)

    arr = np.array(scores, dtype=np.float32)
    if arr.max() > 0:
        arr = arr / arr.max()
    return arr, sr


def _scene_change_scores(
    video_path: str, window_sec: int, hop_sec: int, fps_sample: int = 2
) -> np.ndarray:
    """
    Sample frames at ~fps_sample and measure frame difference to estimate "action".
    Analyze only first ~15 minutes for speed.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return np.array([0.0], dtype=np.float32)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(fps / fps_sample), 1)

    max_frames = int(15 * 60 * fps)  # first 15 minutes
    diffs = []
    prev = None
    idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        idx += 1
        if idx > max_frames:
            break
        if idx % step != 0:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))

        if prev is None:
            prev = gray
            continue

        diff = cv2.absdiff(gray, prev)
        diff_arr = diff.astype("float32")  # ← FIX: explicit ndarray cast
        score = float(diff_arr.mean())

        diffs.append(score)
        prev = gray

    cap.release()

    if not diffs:
        return np.array([0.0], dtype=np.float32)

    diffs = np.array(diffs, dtype=np.float32)
    if diffs.max() > 0:
        diffs = diffs / diffs.max()

    # Convert frame-diff series to windowed scores
    # diffs is sampled at fps_sample, so hop_sec means hop_sec * fps_sample steps
    hop_steps = max(int(hop_sec * fps_sample), 1)
    win_steps = max(int(window_sec * fps_sample), 1)

    if len(diffs) < win_steps:
        return np.array([float(diffs.mean())], dtype=np.float32)

    out = []
    for i in range(0, len(diffs) - win_steps, hop_steps):
        out.append(float(diffs[i : i + win_steps].mean()))

    arr = np.array(out, dtype=np.float32)
    if arr.max() > 0:
        arr = arr / arr.max()
    return arr


def pick_best_highlight(
    video_path: str, wav_cache_path: str, min_sec: int, max_sec: int
) -> Highlight:
    """
    Heuristic:
    - Score windows using audio RMS (hype/loudness) + scene changes (action)
    - Pick best start time in first ~15 mins (fast). You can increase later.
    """
    duration = float(max_sec)

    # 1) audio
    if not os.path.exists(wav_cache_path):
        _extract_audio_wav(video_path, wav_cache_path)

    window_sec = int(duration)
    hop_sec = 2

    audio_scores, _ = _audio_energy_scores(
        wav_cache_path, window_sec=window_sec, hop_sec=hop_sec
    )
    scene_scores = _scene_change_scores(
        video_path, window_sec=window_sec, hop_sec=hop_sec
    )

    # Align lengths
    n = min(len(audio_scores), len(scene_scores))
    if n <= 0:
        return Highlight(start_sec=0.0, duration_sec=duration, score=0.0)

    audio_scores = audio_scores[:n]
    scene_scores = scene_scores[:n]

    # Weighted sum (tune if needed)
    total = (0.65 * audio_scores) + (0.35 * scene_scores)

    best_idx = int(np.argmax(total))
    best_start = float(best_idx * hop_sec)

    # Safety: clamp to min duration range if you want variable durations later
    if duration < min_sec:
        duration = float(min_sec)

    return Highlight(
        start_sec=best_start, duration_sec=float(duration), score=float(total[best_idx])
    )
