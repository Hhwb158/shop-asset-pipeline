"""Tests for video generation step (mocked)."""

from __future__ import annotations

import httpx
import pytest

from shop_pipeline.clients.kling_client import KlingError
from shop_pipeline.steps.generate_video import generate_product_video


def _ok_mp4_bytes() -> bytes:
    """Return minimal MP4 file bytes for download mocking.

    Not a real video — just enough bytes for the file write to succeed.
    """
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16  # fake ftyp box


def test_generate_video_happy_path(tmp_path, monkeypatch):
    """Create task → poll (succeed) → download → write to out_path."""
    task_id = "task-abc"
    video_url = "https://cdn.kling.com/v.mp4"

    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/v1/videos/image2video" in request.url.path and request.method == "POST":
            call_log.append("create")
            return httpx.Response(
                200, json={"code": 0, "data": {"task_id": task_id}, "message": "ok"}
            )
        if request.url.path.endswith(task_id) and request.method == "GET":
            call_log.append("poll")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "task_id": task_id,
                        "task_status": "succeed",
                        "task_result": {"videos": [{"url": video_url, "duration": "5"}]},
                    },
                },
            )
        if str(request.url) == video_url:
            call_log.append("download")
            return httpx.Response(200, content=_ok_mp4_bytes())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    # Stub out ffmpeg postprocess so we don't need real ffmpeg
    from shop_pipeline.steps import generate_video as gv

    monkeypatch.setattr(
        gv, "add_subtitle_to_video", lambda src, dst, txt: src.replace(dst)
    )

    out_path = tmp_path / "out.mp4"
    progress: list[str] = []

    result = generate_product_video(
        api_key="ak",
        api_secret="sk",
        image_url="https://example.com/product.png",
        prompt="slow rotation",
        out_path=out_path,
        duration=5,
        subtitle_text="商品介绍",
        on_progress=progress.append,
        poll_interval_s=0.01,  # speed up test
        client=client,
    )

    assert result.task_id == task_id
    assert result.duration == "5"
    assert out_path.exists()
    assert "create" in call_log
    assert "poll" in call_log
    assert "download" in call_log
    assert progress[0] == "creating-task"


def test_generate_video_times_out(tmp_path):
    """When task never completes, KlingError is raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": {"task_id": "t1"}})
        return httpx.Response(
            200,
            json={"code": 0, "data": {"task_id": "t1", "task_status": "processing"}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    with pytest.raises(KlingError, match="did not complete"):
        generate_product_video(
            api_key="ak",
            api_secret="sk",
            image_url="https://x",
            prompt="p",
            out_path=tmp_path / "out.mp4",
            poll_interval_s=0.01,
            poll_timeout_s=0.05,
            client=client,
        )
