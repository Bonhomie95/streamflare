import os
from typing import Any, Dict, List

import whisper

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = whisper.load_model("base")
    return _model


def transcribe_to_srt(video_path: str, out_srt: str) -> str:
    model = _get_model()

    result: Dict[str, Any] = model.transcribe(
        video_path,
        language="en",
        fp16=False,
        verbose=False,
    )

    segments: List[Dict[str, Any]] = [dict(seg) for seg in result.get("segments", [])]

    os.makedirs(os.path.dirname(out_srt), exist_ok=True)

    with open(out_srt, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start + 1.0))
            text = str(seg.get("text", "")).strip()

            f.write(f"{i}\n")
            f.write(f"{_fmt(start)} --> {_fmt(end)}\n")
            f.write(text + "\n\n")

    return out_srt


def _fmt(seconds: float) -> str:
    total_ms = int(seconds * 1000)
    ms = total_ms % 1000
    s = (total_ms // 1000) % 60
    m = (total_ms // 60000) % 60
    h = total_ms // 3600000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
