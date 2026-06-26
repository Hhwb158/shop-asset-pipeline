"""Video generation step.

Orchestrates: Kling API (image-to-video) → download → ffmpeg post-process.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from shop_pipeline.clients.kling_client import (
    KlingError,
    NotReady,
    VideoResult,
)
from shop_pipeline.clients.kling_client import (
    image_to_video as kling_create,
)
from shop_pipeline.clients.kling_client import (
    poll_video_task as kling_poll,
)
from shop_pipeline.logging_setup import get_logger
from shop_pipeline.steps.postprocess import add_subtitle_to_video

log = get_logger("shop_pipeline.steps.generate_video")


@dataclass(frozen=True)
class VideoOutput:
    """A finished product video on disk."""

    video_path: Path
    duration: str
    task_id: str


def generate_product_video(
    api_key: str,
    api_secret: str,
    image_url: str,
    prompt: str,
    out_path: Path,
    duration: int = 5,
    subtitle_text: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    poll_interval_s: float = 5.0,
    poll_timeout_s: float = 300.0,
    client: httpx.Client | None = None,
) -> VideoOutput:
    """Generate a product video: create Kling task → poll → download → subtitle.

    Args:
        api_key: Kling AK
        api_secret: Kling SK
        image_url: publicly accessible URL of the source image
        prompt: motion description
        out_path: where to save the final .mp4
        duration: 5 or 10 seconds
        subtitle_text: optional Chinese text to overlay as subtitle
        on_progress: optional callback(stage) for UI progress
        poll_interval_s: seconds between polls
        poll_timeout_s: max total wait
        client: optional httpx.Client (for testing)

    Returns:
        VideoOutput with final path
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    http = client or httpx.Client(timeout=120.0)
    try:
        if on_progress:
            on_progress("creating-task")
        log.info("creating Kling video task (duration=%ds)", duration)
        task_id = kling_create(
            api_key=api_key,
            api_secret=api_secret,
            image_url=image_url,
            prompt=prompt,
            duration=duration,
            client=http,
        )
        log.info("task created: %s, polling...", task_id)

        # Poll until ready
        result: VideoResult | None = None
        deadline = time.monotonic() + poll_timeout_s
        while time.monotonic() < deadline:
            try:
                if on_progress:
                    on_progress("polling")
                result = kling_poll(
                    api_key=api_key,
                    api_secret=api_secret,
                    task_id=task_id,
                    timeout_s=10.0,
                    client=http,
                )
                break
            except NotReady as nr:
                log.info("task %s status=%s, waiting %.0fs...", nr.task_id, nr.status, poll_interval_s)
                time.sleep(poll_interval_s)
        if result is None:
            raise KlingError(f"Kling task {task_id} did not complete in {poll_timeout_s}s")

        if on_progress:
            on_progress("downloading")
        # Download to a temp path
        raw_path = out_path.with_suffix(".raw.mp4")
        with http.stream("GET", result.video_url) as resp:
            resp.raise_for_status()
            with raw_path.open("wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        log.info("downloaded to %s", raw_path)

        # Post-process
        if subtitle_text:
            if on_progress:
                on_progress("adding-subtitle")
            add_subtitle_to_video(raw_path, out_path, subtitle_text)
            raw_path.unlink(missing_ok=True)
        else:
            raw_path.replace(out_path)
    finally:
        if own_client:
            http.close()

    return VideoOutput(video_path=out_path, duration=result.duration, task_id=task_id)
