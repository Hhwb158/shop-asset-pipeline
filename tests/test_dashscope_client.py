"""Tests for DashScope image generation client.

All tests use mocked httpx transport — no real API calls.
"""

from __future__ import annotations

import json

import httpx
import pytest

from shop_pipeline.clients.dashscope_client import (
    DashScopeError,
    ImageResult,
    generate_scene_image,
)


def _make_image_response(url: str = "https://cdn.example.com/scene-1.png") -> dict:
    return {
        "output": {
            "task_id": "task-abc-123",
            "results": [{"url": url}],
        },
        "usage": {"image_count": 1},
        "request_id": "req-xyz-789",
    }


def test_generate_scene_image_returns_url(tmp_path):
    """Happy path: client returns image URL from API response."""
    url = "https://cdn.example.com/scene-1.png"
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_make_image_response(url))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    result = generate_scene_image(
        api_key="test-key",
        prompt="product on a wooden desk, warm lighting",
        product_image_path=None,
        aspect_ratio="3:4",
        client=client,
    )

    assert isinstance(result, ImageResult)
    assert result.url == url
    assert result.task_id == "task-abc-123"
    # Verify request was correctly formed
    assert "/api/v1/services/aigc/text2image/image-synthesis" in captured["url"]
    assert captured["json"]["model"] == "qwen-image-plus"
    assert captured["json"]["input"]["prompt"] == "product on a wooden desk, warm lighting"
    # 3:4 aspect ratio should map to 768*1024
    assert captured["json"]["input"]["parameters"]["size"] == "768*1024"


def test_generate_scene_image_with_reference_image(tmp_path):
    """When product_image_path is given, it should be base64-encoded in request."""
    product_img = tmp_path / "product.jpg"
    # Minimal valid JPEG header
    product_img.write_bytes(bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb0043000302020303020303030304030304050805050404050a070706080c0a0c0c0b0a0b0b0d0e12100d0e110e0b0b1016100e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0effd9"))

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_make_image_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    generate_scene_image(
        api_key="test-key",
        prompt="product in lifestyle scene",
        product_image_path=product_img,
        aspect_ratio="16:9",
        client=client,
    )

    # Verify reference image was base64-encoded into parameters
    params = captured["json"]["input"]["parameters"]
    assert "ref_img" in params
    assert params["ref_img"].startswith("data:image/jpeg;base64,")


def test_generate_scene_image_retries_on_5xx():
    """Retries up to 3 times on server errors, then raises."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(500, json={"message": "internal error"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    with pytest.raises(DashScopeError, match="500"):
        generate_scene_image(
            api_key="test-key",
            prompt="test",
            client=client,
        )
    # 1 initial + 2 retries = 3
    assert call_count["n"] == 3


def test_generate_scene_image_no_retry_on_4xx():
    """Client errors (4xx) are not retried."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401, json={"message": "invalid api key"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    with pytest.raises(DashScopeError, match="401"):
        generate_scene_image(api_key="bad-key", prompt="test", client=client)
    assert call_count["n"] == 1


def test_generate_scene_image_empty_results_raises():
    """When API returns no results, raise clear error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": {"results": []}})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    with pytest.raises(DashScopeError, match="no images"):
        generate_scene_image(api_key="k", prompt="p", client=client)
