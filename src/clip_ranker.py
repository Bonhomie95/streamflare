from datetime import datetime, timezone
from typing import Any, Dict, List


def _hours_ago(ts: str) -> float:
    created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - created
    return max(delta.total_seconds() / 3600.0, 0.1)


def _duration_weight(seconds: float) -> float:
    """
    Ideal Shorts duration ~25–45s
    """
    if seconds < 10:
        return 0.3
    if 20 <= seconds <= 45:
        return 1.0
    if seconds <= 60:
        return 0.8
    return 0.4


def _recency_weight(hours_ago: float) -> float:
    if hours_ago <= 6:
        return 1.3
    if hours_ago <= 24:
        return 1.0
    if hours_ago <= 48:
        return 0.8
    return 0.5


def score_clip(clip: Dict[str, Any]) -> float:
    views = float(clip.get("view_count", 0))
    duration = float(clip.get("duration", 0))
    created_at = clip.get("created_at")

    if not created_at or views <= 0:
        return 0.0

    hours_ago = _hours_ago(created_at)

    score = views * _duration_weight(duration) * _recency_weight(hours_ago)

    return score


def pick_best_clip(clips: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = sorted(
        clips,
        key=score_clip,
        reverse=True,
    )
    return ranked[0]
