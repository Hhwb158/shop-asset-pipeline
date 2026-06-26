"""Post-process video / audio with ffmpeg.

Currently supports: add a hardcoded Chinese subtitle to a video.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from shop_pipeline.logging_setup import get_logger

log = get_logger("shop_pipeline.steps.postprocess")


class FFmpegError(RuntimeError):
    """Raised when ffmpeg fails."""


def check_ffmpeg_available() -> bool:
    """Return True if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def add_subtitle_to_video(src: Path, dst: Path, text: str) -> None:
    """Burn `text` as a hardcoded subtitle to the bottom of the video.

    Uses ffmpeg's drawtext filter. Requires a CJK-capable font on the system
    (e.g. on Windows we use the built-in Microsoft YaHei).

    Raises:
        FFmpegError: ffmpeg missing or failed
    """
    if not check_ffmpeg_available():
        raise FFmpegError(
            "ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html"
        )
    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    # Windows ships Microsoft YaHei UI at a stable path; Linux users can edit this
    font_candidates = [
        "C:/Windows/Fonts/msyh.ttc",  # Microsoft YaHei (CJK)
        "C:/Windows/Fonts/msyh.ttf",
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)
    font_arg = "" if font_path is None else f"fontfile={font_path}:"

    # Escape colons, single quotes, backslashes for ffmpeg drawtext
    safe_text = (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    drawtext = (
        f"drawtext=text='{safe_text}':{font_arg}fontcolor=white:fontsize=42:"
        f"box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h-th-40"
    )

    cmd = [
        "ffmpeg",
        "-y",  # overwrite
        "-i",
        str(src),
        "-vf",
        drawtext,
        "-codec:a",
        "copy",
        str(dst),
    ]
    log.info("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed: {proc.stderr[-500:]}")
