import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    twitch_client_id: str
    twitch_client_secret: str
    broadcaster_ids: list[str]

    highlight_min_sec: int
    highlight_max_sec: int

    brand_name: str

    root_dir: str
    assets_dir: str
    cache_dir: str
    twitch_cache_dir: str
    vod_dir: str
    audio_dir: str
    renders_dir: str
    logs_dir: str

    logo_path: str
    subscribe_path: str


def _split_csv(value: str) -> list[str]:
    items = []
    for x in (value or "").split(","):
        x = x.strip()
        if x:
            items.append(x)
    return items


def get_settings() -> Settings:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    cache_dir = os.path.join(root, "cache")
    twitch_cache = os.path.join(cache_dir, "twitch")
    vod_dir = os.path.join(twitch_cache, "vods")
    audio_dir = os.path.join(twitch_cache, "audio")
    renders_dir = os.path.join(cache_dir, "renders")
    logs_dir = os.path.join(cache_dir, "logs")
    assets_dir = os.path.join(root, "assets")

    os.makedirs(vod_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(renders_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    return Settings(
        twitch_client_id=os.getenv("TWITCH_CLIENT_ID", "").strip(),
        twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", "").strip(),
        broadcaster_ids=_split_csv(os.getenv("TWITCH_BROADCASTER_IDS", "")),
        highlight_min_sec=int(os.getenv("HIGHLIGHT_MIN_SEC", "40")),
        highlight_max_sec=int(os.getenv("HIGHLIGHT_MAX_SEC", "60")),
        brand_name=os.getenv("BRAND_NAME", "Stream Flare").strip(),
        root_dir=root,
        assets_dir=assets_dir,
        cache_dir=cache_dir,
        twitch_cache_dir=twitch_cache,
        vod_dir=vod_dir,
        audio_dir=audio_dir,
        renders_dir=renders_dir,
        logs_dir=logs_dir,
        logo_path=os.path.join(assets_dir, "logo.png"),
        subscribe_path=os.path.join(assets_dir, "subscribe.png"),
    )
