import os
import subprocess
from dataclasses import dataclass

from .utils import safe_filename


@dataclass
class RenderResult:
    output_path: str


def _ffmpeg_escape_path(p: str) -> str:
    # FFmpeg subtitles filter on Windows behaves best with forward slashes
    return p.replace("\\", "/").replace(":", "\\:")


def render_shorts(
    input_path: str,
    output_path: str,
    start_sec: float,
    duration_sec: float,
    logo_path: str,
    subscribe_path: str,
    subtitles_path: str | None = None,
) -> RenderResult:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logo_w = 170
    sub_w = 220

    # Build base chain with labels
    # End output labeled as [v]
    base_vf = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "gblur=sigma=25[bg];"
        "[0:v]scale=940:1680:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[1:v]scale={logo_w}:-1[logo];"
        f"[2:v]scale={sub_w}:-1[sub];"
        "[base][logo]overlay=40:40[tmp];"
        "[tmp][sub]overlay=W-w-40:H-h-60[v]"
    )

    # If subtitles enabled, apply on [v] and output as [vs]
    vf = base_vf
    map_label = "[v]"

    if subtitles_path:
        sub_file = _ffmpeg_escape_path(subtitles_path)
        vf += (
            f";{map_label}subtitles='{sub_file}':"
            "force_style='Fontsize=14,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2,Alignment=2'[vs]"
        )
        map_label = "[vs]"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        input_path,
        "-i",
        logo_path,
        "-i",
        subscribe_path,
        "-t",
        str(duration_sec),
        "-filter_complex",
        vf,
        "-map",
        map_label,
        "-map",
        "0:a?",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed:\n{p.stderr}")

    return RenderResult(output_path=output_path)
