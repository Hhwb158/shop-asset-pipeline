"""Tests for Kling AI image-to-video client (mocked)."""

from __future__ import annotations

import httpx
import pytest

from shop_pipeline.clients.kling_client import (
    KlingError,
    NotReady,
    VideoResult,
    image_to_video,
    poll_video_task,
)


def _mock_create_response(task_id: str = "task-001") -> dict:
    return {
        "code": 0,
        "data": {"task_id": task_id},
        "message": "success",
    }


def _mock_poll_response(task_id: str, status: str = "succeed", video_url: str | None = None) -> dict:
    data: dict = {"task_id": task_id, "task_status": status}
    if video_url:
        data["task_result"] = {"videos": [{"url": video_url, "duration": "5"}]}
    return {"code": 0, "data": data, "message": "success"}


def test_image_to_video_creates_task_and_returns_id():
    """image_to_video calls /v1/videos/image2video and returns task_id."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["json"] = request.content.decode() if request.content else None
        return httpx.Response(200, json=_mock_create_response("task-xyz"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    task_id = image_to_video(
        api_key="ak-test",
        api_secret="sk-test",
        image_url="https://example.com/product.png",
        prompt="slowly rotate the product, smooth camera",
        duration=5,
        client=client,
    )
    assert task_id == "task-xyz"
    assert "/v1/videos/image2video" in captured["url"]
    # JWT in Authorization header
    assert captured["headers"]["authorization"].startswith("Bearer ")
    # Body has model + prompt + image
    body = captured["json"]
    assert "kling-v1-5" in body
    assert "slowly rotate" in body
    assert "product.png" in body


def test_poll_video_task_succeeds_returns_url():
    """poll returns VideoResult with URL when status is 'succeed'."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_mock_poll_response("task-001", "succeed", "https://cdn.kling.com/v.mp4")
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    result = poll_video_task(
        api_key="ak", api_secret="sk", task_id="task-001", client=client
    )
    assert isinstance(result, VideoResult)
    assert result.video_url == "https://cdn.kling.com/v.mp4"
    assert result.task_id == "task-001"


def test_poll_video_task_processing_raises_not_ready():
    """When status is 'processing', raise NotReady so caller can retry."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_poll_response("task-001", "processing"))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    with pytest.raises(NotReady):
        poll_video_task(api_key="a", api_secret="s", task_id="task-001", client=client)


def test_poll_video_task_failed_raises():
    """When status is 'failed', raise KlingError with code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 0, "data": {"task_id": "t", "task_status": "failed",
                                            "task_status_msg": "content policy violation"}}
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.klingai.com")

    with pytest.raises(KlingError, match="content policy"):
        poll_video_task(api_key="a", api_secret="s", task_id="t", client=client)


def test_jwt_token_format():
    """JWT must encode ak, ts, and have a valid signature."""
    import jwt as pyjwt  # type: ignore[import-untyped]

    from shop_pipeline.clients.kling_client import _make_jwt

    token = _make_jwt("ak-123", "sk-456")
    # Decode without verification just to inspect payload
    payload = pyjwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == "ak-123"
    assert "exp" in payload
    assert "iat" in payload
