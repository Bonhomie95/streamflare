from typing import Any, Dict, Optional
from .utils import read_json, write_json, utc_ts


def _load_state(state_path: str) -> Dict[str, Any]:
    """
    Load full shared state without overwriting unrelated keys.
    """
    return read_json(
        state_path,
        default={
            "last_index": -1,
            "used_vods": [],
            "used_clips": [],
            "updated_at": None,
        },
    )


def _save_state(state_path: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = utc_ts()
    write_json(state_path, state)


def pick_next_broadcaster_id(
    broadcaster_ids: list[str],
    state_path: str,
) -> str:
    if not broadcaster_ids:
        raise ValueError("TWITCH_BROADCASTER_IDS is empty.")

    state = _load_state(state_path)

    last_index = int(state.get("last_index", -1))
    next_index = (last_index + 1) % len(broadcaster_ids)

    state["last_index"] = next_index
    _save_state(state_path, state)

    return broadcaster_ids[next_index]


def choose_vod(
    vods: list[Dict[str, Any]],
    state_path: str,
) -> Optional[Dict[str, Any]]:
    """
    Select the first VOD that has NOT been used before.
    If all VODs are used → return None (do NOT repeat).
    """

    if not vods:
        return None

    state = _load_state(state_path)
    used_vods = set(state.get("used_vods", []))

    for vod in vods:
        vod_id = vod.get("id")
        if not vod_id:
            continue

        if vod_id not in used_vods:
            used_vods.add(vod_id)
            state["used_vods"] = list(used_vods)[-100:]  # keep last 100
            _save_state(state_path, state)
            return vod

    # 🚫 All VODs already used — do NOT repeat
    return None
