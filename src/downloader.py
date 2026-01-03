import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from .utils import safe_filename, sha1


@dataclass
class DownloadResult:
    vod_path: str
    vod_url: str


def download_twitch_vod(
    vod_url: str, out_dir: str, prefer_height: int = 720
) -> DownloadResult:
    """
    Uses yt-dlp to download Twitch VOD.
    """
    os.makedirs(out_dir, exist_ok=True)

    key = sha1(vod_url)
    out_template = os.path.join(out_dir, f"{key}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        f"bestvideo[height<={prefer_height}]+bestaudio/best[height<={prefer_height}]/best",
        "-o",
        out_template,
        vod_url,
    ]

    p = subprocess.run(cmd)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{p.stderr}")

    # Find the downloaded file by key prefix
    downloaded = None
    for name in os.listdir(out_dir):
        if name.startswith(key + "_"):
            downloaded = os.path.join(out_dir, name)
            break

    if not downloaded:
        raise RuntimeError("Download succeeded but output file not found.")

    # Clean filename (optional)
    base = os.path.basename(downloaded)
    safe = safe_filename(base)
    safe_path = os.path.join(out_dir, safe)
    if safe_path != downloaded:
        os.replace(downloaded, safe_path)
        downloaded = safe_path

    return DownloadResult(vod_path=downloaded, vod_url=vod_url)

def download_twitch_clip(clip_url: str, out_dir: str) -> DownloadResult:
    os.makedirs(out_dir, exist_ok=True)

    key = sha1(clip_url)
    out_template = os.path.join(out_dir, f"{key}_%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "best",
        "-o",
        out_template,
        clip_url,
    ]

    subprocess.run(cmd, check=True)

    for name in os.listdir(out_dir):
        if name.startswith(key + "_"):
            path = os.path.join(out_dir, name)
            safe = safe_filename(name)
            safe_path = os.path.join(out_dir, safe)
            if safe_path != path:
                os.replace(path, safe_path)
            return DownloadResult(vod_path=safe_path, vod_url=clip_url)

    raise RuntimeError("Clip download failed")
