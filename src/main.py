import os

from .config import get_settings
from .twitch_client import TwitchClient
from .vod_finder import pick_next_broadcaster_id, choose_vod
from .downloader import download_twitch_vod, download_twitch_clip
from .highlight_picker import pick_best_highlight
from .editor import render_shorts
from .utils import read_json, write_json, safe_filename, sha1, utc_ts
from .clip_ranker import pick_best_clip
from .subtitles import transcribe_to_srt
from .youtube_uploader import upload_video


# mode: "vods" or "clips"
mode = os.getenv("TWITCH_MODE", "vods").lower()


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


def main() -> None:
    s = get_settings()

    if not s.twitch_client_id or not s.twitch_client_secret:
        raise ValueError("Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET")
    if not s.broadcaster_ids:
        raise ValueError("Missing TWITCH_BROADCASTER_IDS")
    if not os.path.exists(s.logo_path):
        raise FileNotFoundError(f"Missing logo: {s.logo_path}")
    if not os.path.exists(s.subscribe_path):
        raise FileNotFoundError(f"Missing subscribe icon: {s.subscribe_path}")

    state_path = os.path.join(s.cache_dir, "state.json")
    read_json(state_path, default={})  # ensure exists

    # 🔁 Round-robin broadcaster selection
    broadcaster_id = pick_next_broadcaster_id(s.broadcaster_ids, state_path=state_path)

    twitch = TwitchClient(s.twitch_client_id, s.twitch_client_secret)
    user = twitch.get_user(broadcaster_id)
    broadcaster_name = user.get("display_name") or user.get("login") or broadcaster_id

    print(f"\n🎮 Broadcaster: {broadcaster_name}")
    print(f"⚙️ Mode: {mode.upper()}")

    # =====================================================
    # 🎬 CLIPS MODE (FAST, VIRAL)
    # =====================================================
    if mode == "clips":
        lookback_hours = int(os.getenv("CLIPS_LOOKBACK_HOURS", "48"))
        clips = twitch.get_top_clips(
            broadcaster_id=broadcaster_id,
            lookback_hours=lookback_hours,
            limit=10,
        )

        if not clips:
            print("❌ No clips found.")
            return

        clip = pick_best_clip(clips)
        vod_id = clip["id"]
        vod_title = clip.get("title", "")
        vod_url = clip["url"]
        game_name = clip.get("game_name", "")

        print(f"🔥 Clip: {vod_title}")
        print(f"🔗 URL: {vod_url}")

        dl = download_twitch_clip(vod_url, out_dir=s.vod_dir)
        print("✅ Downloaded clip:", dl.vod_path)

        highlight_start = 0.0
        highlight_duration = min(
            float(clip.get("duration", 60)), float(s.highlight_max_sec)
        )
        highlight_score = 1.0  # clips are already curated

    # =====================================================
    # 📼 VODS MODE (UNCHANGED)
    # =====================================================
    else:
        vods = twitch.get_latest_vods(broadcaster_id, limit=5)
        vod = choose_vod(vods, state_path=state_path)

        if not vod:
            print("❌ No VOD found.")
            return

        vod_id = vod.get("id")
        vod_title = vod.get("title", "")
        vod_url = vod.get("url", "")
        game_id = vod.get("game_id", "")

        game = twitch.get_game(game_id)
        game_name = game.get("name", "")

        print(f"📼 VOD: {vod_title}")
        print(f"🔗 URL: {vod_url}")

        dl = download_twitch_vod(vod_url, out_dir=s.vod_dir, prefer_height=720)
        print("✅ Downloaded:", dl.vod_path)

        wav_cache = os.path.join(s.audio_dir, f"{sha1(dl.vod_path)}.wav")
        highlight = pick_best_highlight(
            video_path=dl.vod_path,
            wav_cache_path=wav_cache,
            min_sec=s.highlight_min_sec,
            max_sec=s.highlight_max_sec,
        )

        highlight_start = highlight.start_sec
        highlight_duration = highlight.duration_sec
        highlight_score = highlight.score

        print(
            f"✨ Highlight start={highlight_start:.1f}s "
            f"dur={highlight_duration:.1f}s "
            f"score={highlight_score:.3f}"
        )

    # =====================================================
    # 🎞️ RENDER SHORT
    # =====================================================
    # =====================================================
    # 🎞️ RENDER SHORT
    # =====================================================
    render_key = sha1(f"{dl.vod_path}|{highlight_start:.1f}|{highlight_duration:.1f}")
    out_name = safe_filename(f"{broadcaster_name}_{vod_id}_{render_key}.mp4")
    out_path = os.path.join(s.renders_dir, out_name)

    srt_path = out_path.replace(".mp4", ".srt")

    # 1) Render base short first (no subtitles) if not exists
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
            subtitles_path=None,  # base render first
        )
    print("🎬 Rendered base:", rr.output_path)

    # 2) Generate subtitles from the rendered short (timestamps match!)
    if not os.path.exists(srt_path):
        print("📝 Generating subtitles...")
    transcribe_to_srt(out_path, srt_path)

    # 3) Burn subtitles (create a new file then replace)
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

    # replace original with subbed version
    os.replace(out_subbed, out_path)

    # =====================================================
    # 🧾 METADATA
    # =====================================================
    title, desc, tags = build_title_and_description(
        brand=s.brand_name,
        broadcaster=broadcaster_name,
        vod_title=vod_title,
        game_name=game_name,
    )

    meta = {
        "created_at": utc_ts(),
        "mode": mode,
        "broadcaster_id": broadcaster_id,
        "broadcaster_name": broadcaster_name,
        "source_id": vod_id,
        "source_title": vod_title,
        "source_url": vod_url,
        "game_name": game_name,
        "highlight": {
            "start_sec": highlight_start,
            "duration_sec": highlight_duration,
            "score": highlight_score,
        },
        "render_path": out_path,
        "youtube": {
            "title": title,
            "description": desc,
            "hashtags": tags,
        },
    }

    meta_path = out_path + ".json"
    write_json(meta_path, meta)

    resp = upload_video(
        file_path=out_path,
        title=meta["youtube"]["title"],
        description=meta["youtube"]["description"],
        tags=meta["youtube"]["hashtags"],
        privacy="public",  # or "unlisted" / "private"
    )
    print("🎉 Uploaded to YouTube:", resp["id"])

    print("\n🧾 YouTube Metadata")
    print("Title:", title)
    print("Description preview:", desc[:160].replace("\n", " "), "...")
    print("\n✅ DONE")
    print("🎞️ Render:", out_path)
    print("📄 Meta:", meta_path)


if __name__ == "__main__":
    main()
