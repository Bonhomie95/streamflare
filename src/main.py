# src/main.py
import os
from typing import Any, Dict, List, Optional

from .config import get_settings
from .twitch_client import TwitchClient
from .vod_finder import pick_next_broadcaster_id, choose_vod
from .downloader import download_twitch_vod, download_twitch_clip
from .highlight_picker import pick_best_highlight
from .editor import render_shorts
from .utils import read_json, write_json, safe_filename, sha1, utc_ts
from .clip_ranker import score_clip  # ✅ use score_clip so we can skip used clips
from .subtitles import transcribe_to_srt
from .youtube_uploader import upload_video

# mode: "vods" or "clips"
MODE = os.getenv("TWITCH_MODE", "vods").lower()


def build_title_and_description(
    brand: str, broadcaster: str, vod_title: str, game_name: str
) -> tuple[str, str, list[str]]:
    game = game_name.strip() if game_name else "Twitch"
    base_title = vod_title.strip() if vod_title else f"{broadcaster} Highlight"
    title = f"{base_title} | {broadcaster} ({game}) #shorts"

    hashtags = ["#shorts", "#twitch", "#twitchclips", "#gaming"]
    game_tag = "#" + "".join(c for c in game if c.isalnum())
    if len(game_tag) > 2:
        hashtags.insert(0, game_tag)

    desc = (
        f"{base_title}\n\n"
        f"Creator: {broadcaster}\n"
        f"Game: {game}\n\n"
        f"Uploaded by: {brand}\n\n" + " ".join(hashtags[:10])
    )

    return title, desc, hashtags


def _load_state(state_path: str) -> Dict[str, Any]:
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


def _pick_best_unused_clip(
    clips: List[Dict[str, Any]], used_clip_ids: set[str]
) -> Optional[Dict[str, Any]]:
    # rank by your formula: views × duration weight × recency weight
    ranked = sorted(clips, key=score_clip, reverse=True)
    for c in ranked:
        cid = c.get("id")
        if cid and cid not in used_clip_ids:
            return c
    return None


def main() -> None:
    s = get_settings()

    # -----------------------
    # Validate config/assets
    # -----------------------
    if not s.twitch_client_id or not s.twitch_client_secret:
        raise ValueError("Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET")
    if not s.broadcaster_ids:
        raise ValueError("Missing TWITCH_BROADCASTER_IDS")
    if not os.path.exists(s.logo_path):
        raise FileNotFoundError(f"Missing logo: {s.logo_path}")
    if not os.path.exists(s.subscribe_path):
        raise FileNotFoundError(f"Missing subscribe icon: {s.subscribe_path}")

    state_path = os.path.join(s.cache_dir, "state.json")
    state = _load_state(state_path)

    # -----------------------
    # Round-robin broadcaster
    # -----------------------
    broadcaster_id = pick_next_broadcaster_id(s.broadcaster_ids, state_path=state_path)

    twitch = TwitchClient(s.twitch_client_id, s.twitch_client_secret)
    user = twitch.get_user(broadcaster_id)
    broadcaster_name = user.get("display_name") or user.get("login") or broadcaster_id

    print(f"\n🎮 Broadcaster: {broadcaster_name}")
    print(f"⚙️ Mode: {MODE.upper()}")

    # -----------------------
    # Shared variables
    # -----------------------
    source_id = ""
    source_title = ""
    source_url = ""
    game_name = ""

    dl = None
    highlight_start = 0.0
    highlight_duration = 0.0
    highlight_score = 0.0

    # =====================================================
    # 🎬 CLIPS MODE
    # =====================================================
    if MODE == "clips":
        lookback_hours = int(os.getenv("CLIPS_LOOKBACK_HOURS", "48"))

        clips = twitch.get_top_clips(
            broadcaster_id=broadcaster_id,
            lookback_hours=lookback_hours,
            limit=20,  # ✅ a bit more so we can skip used clips
        )

        if not clips:
            print("❌ No clips found.")
            return

        used_clips = set(state.get("used_clips", []))
        clip = _pick_best_unused_clip(clips, used_clips)

        if not clip:
            print("🚫 All fetched clips have already been used — skipping this cycle.")
            return

        source_id = str(clip.get("id", ""))
        source_title = str(clip.get("title", ""))
        source_url = str(clip.get("url", ""))
        game_name = str(clip.get("game_name", ""))

        print(f"🔥 Clip: {source_title}")
        print(f"🔗 URL: {source_url}")

        dl = download_twitch_clip(source_url, out_dir=s.vod_dir)
        print("✅ Downloaded clip:", dl.vod_path)

        highlight_start = 0.0
        highlight_duration = min(
            float(clip.get("duration", 60.0)), float(s.highlight_max_sec)
        )
        highlight_score = float(score_clip(clip))

        # ✅ mark clip as used immediately (prevents repeats even if later steps crash)
        used_clips.add(source_id)
        state["used_clips"] = list(used_clips)[-150:]
        _save_state(state_path, state)

    # =====================================================
    # 📼 VODS MODE
    # =====================================================
    else:
        vods = twitch.get_latest_vods(broadcaster_id, limit=5)
        vod = choose_vod(vods, state_path=state_path)

        # ✅ choose_vod now returns None when everything was used
        if not vod:
            print("🚫 No unused VOD found — skipping this cycle.")
            return

        source_id = str(vod.get("id", ""))
        source_title = str(vod.get("title", ""))
        source_url = str(vod.get("url", ""))
        game_id = str(vod.get("game_id", ""))

        game = twitch.get_game(game_id) if game_id else {}
        game_name = str(game.get("name", ""))

        print(f"📼 VOD: {source_title}")
        print(f"🔗 URL: {source_url}")

        dl = download_twitch_vod(source_url, out_dir=s.vod_dir, prefer_height=720)
        print("✅ Downloaded:", dl.vod_path)

        wav_cache = os.path.join(s.audio_dir, f"{sha1(dl.vod_path)}.wav")
        highlight = pick_best_highlight(
            video_path=dl.vod_path,
            wav_cache_path=wav_cache,
            min_sec=s.highlight_min_sec,
            max_sec=s.highlight_max_sec,
        )

        highlight_start = float(highlight.start_sec)
        highlight_duration = float(highlight.duration_sec)
        highlight_score = float(highlight.score)

        print(
            f"✨ Highlight start={highlight_start:.1f}s "
            f"dur={highlight_duration:.1f}s "
            f"score={highlight_score:.3f}"
        )

    if dl is None:
        print("❌ Internal error: download result is missing.")
        return

    # =====================================================
    # 🎞️ Render paths (cache key)
    # =====================================================
    render_key = sha1(f"{dl.vod_path}|{highlight_start:.1f}|{highlight_duration:.1f}")
    out_name = safe_filename(f"{broadcaster_name}_{source_id}_{render_key}.mp4")
    out_path = os.path.join(s.renders_dir, out_name)
    srt_path = out_path.replace(".mp4", ".srt")

    # =====================================================
    # 🎞️ 1) Render base short (NO subtitles)
    # =====================================================
    if os.path.exists(out_path):
        print("♻️ Render exists:", out_path)
    else:
        rr = render_shorts(
            input_path=dl.vod_path,
            output_path=out_path,
            start_sec=highlight_start,
            duration_sec=highlight_duration,
            logo_path=s.logo_path,
            subscribe_path=s.subscribe_path,
            subtitles_path=None,
        )
        print("🎬 Rendered base:", rr.output_path)

    print("🎬 Base render path:", out_path)

    # =====================================================
    # 📝 2) Generate subtitles (optional)
    # =====================================================
    subtitles_ready = False
    if os.getenv("ENABLE_SUBTITLES", "true").lower() == "true":
        if not os.path.exists(srt_path):
            print("📝 Generating subtitles...")
            try:
                transcribe_to_srt(out_path, srt_path)  # ✅ transcribe the final short
            except Exception as e:
                print("⚠️ Subtitle generation failed:", e)

        if os.path.exists(srt_path):
            subtitles_ready = True
            print("✅ Subtitles ready:", srt_path)
        else:
            print("⚠️ Subtitles missing, skipping burn step")
    else:
        print("🚫 Subtitles disabled by config")

    # =====================================================
    # 🔥 3) Burn subtitles ONLY IF ready
    # =====================================================
    if subtitles_ready:
        out_subbed = out_path.replace(".mp4", "_subbed.mp4")

        if not os.path.exists(out_subbed):
            print("🔥 Burning subtitles...")
            rr2 = render_shorts(
                input_path=dl.vod_path,
                output_path=out_subbed,
                start_sec=highlight_start,
                duration_sec=highlight_duration,
                logo_path=s.logo_path,
                subscribe_path=s.subscribe_path,
                subtitles_path=srt_path,
            )
            print("✅ Subbed render:", rr2.output_path)

        if os.path.exists(out_subbed):
            os.replace(out_subbed, out_path)
            print("♻️ Replaced base with subbed:", out_path)
    else:
        print("➡️ Using base render (no subtitles)")

    # =====================================================
    # 🧾 4) Metadata
    # =====================================================
    title, desc, tags = build_title_and_description(
        brand=s.brand_name,
        broadcaster=broadcaster_name,
        vod_title=source_title,
        game_name=game_name,
    )

    meta = {
        "created_at": utc_ts(),
        "mode": MODE,
        "broadcaster_id": broadcaster_id,
        "broadcaster_name": broadcaster_name,
        "source_id": source_id,
        "source_title": source_title,
        "source_url": source_url,
        "game_name": game_name,
        "highlight": {
            "start_sec": highlight_start,
            "duration_sec": highlight_duration,
            "score": highlight_score,
        },
        "render_path": out_path,
        "subtitles_path": srt_path if subtitles_ready else None,
        "youtube": {
            "title": title,
            "description": desc,
            "hashtags": tags,
        },
    }

    meta_path = out_path + ".json"
    write_json(meta_path, meta)

    # =====================================================
    # 🚀 5) Upload YouTube
    # =====================================================
    resp = upload_video(
        file_path=out_path,
        title=title,
        description=desc,
        tags=tags,
        privacy="public",
    )
    print("🎉 Uploaded to YouTube:", resp.get("id"))

    print("\n✅ DONE")
    print("🎞️ Render:", out_path)
    print("📄 Meta:", meta_path)


if __name__ == "__main__":
    main()
