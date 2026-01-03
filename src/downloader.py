import os
import subprocess
import sys
from dataclasses import dataclass

from .utils import safe_filename, sha1


@dataclass
class DownloadResult:
    vod_path: str
    vod_url: str


def _yt_dlp_cmd():
    """
    Always call yt-dlp via the current Python executable.
    This works reliably under systemd.
    """
    return [sys.executable, "-m", "yt_dlp"]


def download_twitch_vod(
    vod_url: str, out_dir: str, prefer_height: int = 720
) -> DownloadResult:
    os.makedirs(out_dir, exist_ok=True)

    key = sha1(vod_url)
    out_template = os.path.join(out_dir, f"{key}_%(title)s.%(ext)s")

    cmd = _yt_dlp_cmd() + [
        "-f",
        f"bestvideo[height<={prefer_height}]+bestaudio/"
        f"best[height<={prefer_height}]/best",
        "-o",
        out_template,
        vod_url,
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{p.stderr}")

    downloaded = None
    for name in os.listdir(out_dir):
        if name.startswith(key + "_"):
            downloaded = os.path.join(out_dir, name)
            break

    if not downloaded:
        raise RuntimeError("Download succeeded but output file not found.")

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

    cmd = _yt_dlp_cmd() + [
        "-f",
        "best",
        "-o",
        out_template,
        clip_url,
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp clip failed:\n{p.stderr}")

    for name in os.listdir(out_dir):
        if name.startswith(key + "_"):
            path = os.path.join(out_dir, name)
            safe = safe_filename(name)
            safe_path = os.path.join(out_dir, safe)
            if safe_path != path:
                os.replace(path, safe_path)
            return DownloadResult(vod_path=safe_path, vod_url=clip_url)

    raise RuntimeError("Clip download failed")
