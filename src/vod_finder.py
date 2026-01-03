from typing import Any, Dict, Optional
from .utils import read_json, write_json, utc_ts


def pick_next_broadcaster_id(broadcaster_ids: list[str], state_path: str) -> str:
    if not broadcaster_ids:
        raise ValueError("TWITCH_BROADCASTER_IDS is empty.")

    state = read_json(state_path, default={"last_index": -1, "updated_at": None})
    last_index = int(state.get("last_index", -1))

    next_index = (last_index + 1) % len(broadcaster_ids)
    state["last_index"] = next_index
    state["updated_at"] = utc_ts()
    write_json(state_path, state)

    return broadcaster_ids[next_index]


def choose_vod(vods: list[Dict[str, Any]], state_path: str) -> Optional[Dict[str, Any]]:
    """
    Prefer a VOD we haven't used recently.
    Keeps a small 'used_vods' list in state.json.
    """
    state = read_json(state_path, default={"used_vods": []})
    used = set(state.get("used_vods", []))

    for v in vods:
        vid = v.get("id")
        if vid and vid not in used:
            used.add(vid)
            state["used_vods"] = list(used)[-50:]  # keep last 50
            write_json(state_path, state)
            return v

    # If all used, just return the newest
    return vods[0] if vods else None
