"""Tests for MiniMax image generation client (mocked)."""

from __future__ import annotations

import httpx
import pytest

from shop_pipeline.clients.minimax_image_client import (
    MiniMaxErrorCode,
    MiniMaxImageError,
    _is_retryable,
    generate_image,
    generate_image_with_subject,
)


def _ok_response(urls: list[str] | None = None, b64: list[str] | None = None) -> dict:
    urls = urls or ["https://cdn.minimaxi.com/img1.png"]
    return {
        "id": "task-001",
        "data": {"image_urls": urls, "image_base64": b64 or []},
        "metadata": {"success_count": len(urls), "failed_count": 0},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


def test_generate_text_to_image_returns_url():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.content.decode() if request.content else None
        return httpx.Response(200, json=_ok_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")

    result = generate_image(
        api_key="sk-test",
        prompt="a red ceramic mug on a wooden table",
        aspect_ratio="3:4",
        n=1,
        client=client,
    )
    assert result.urls == ["https://cdn.minimaxi.com/img1.png"]
    assert result.task_id == "task-001"
    # Verify auth and endpoint
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert "/v1/image_generation" in captured["url"]
    # Verify body
    import json as _json

    body = _json.loads(captured["json"])
    assert body["model"] == "image-01"
    assert body["prompt"] == "a red ceramic mug on a wooden table"
    assert body["aspect_ratio"] == "3:4"
    assert body["response_format"] == "url"


def test_generate_with_subject_reference_sends_subject_reference_field():
    """When image_url is provided, request includes subject_reference."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.content.decode() if request.content else None
        return httpx.Response(200, json=_ok_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")

    result = generate_image_with_subject(
        api_key="sk",
        prompt="the same product on a beach",
        subject_image_url="https://example.com/product.png",
        subject_type="character",
        aspect_ratio="16:9",
        client=client,
    )
    import json as _json
    body = _json.loads(captured["json"])
    assert "subject_reference" in body
    assert body["subject_reference"][0]["type"] == "character"
    assert body["subject_reference"][0]["image_file"] == "https://example.com/product.png"
    assert result.urls == ["https://cdn.minimaxi.com/img1.png"]


def test_generate_returns_multiple_urls_when_n_greater_than_1():
    urls = [f"https://cdn.minimaxi.com/img{i}.png" for i in range(3)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_response(urls=urls))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")

    result = generate_image(api_key="k", prompt="p", n=3, client=client)
    assert len(result.urls) == 3


def test_generate_no_urls_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {"image_urls": [], "image_base64": []},
            "base_resp": {"status_code": 0},
        })
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    with pytest.raises(MiniMaxImageError, match="no images"):
        generate_image(api_key="k", prompt="p", client=client)


def test_generate_retries_on_rate_limit_1002():
    """1002 (rate limited) is retried up to 2 times."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(200, json={
                "base_resp": {"status_code": 1002, "status_msg": "rate limited"}
            })
        return httpx.Response(200, json=_ok_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    # Patch sleep to keep test fast
    import shop_pipeline.clients.minimax_image_client as mod
    orig_sleep = mod.time.sleep
    mod.time.sleep = lambda s: None
    try:
        result = generate_image(api_key="k", prompt="p", client=client)
        assert result.urls == ["https://cdn.minimaxi.com/img1.png"]
        assert call_count["n"] == 3
    finally:
        mod.time.sleep = orig_sleep


def test_generate_does_not_retry_on_insufficient_balance_1008():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={
            "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}
        })

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    with pytest.raises(MiniMaxImageError) as exc:
        generate_image(api_key="k", prompt="p", client=client)
    assert exc.value.code == MiniMaxErrorCode.INSUFFICIENT_BALANCE
    assert call_count["n"] == 1


def test_generate_does_not_retry_on_auth_failure_1004():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={
            "base_resp": {"status_code": 1004, "status_msg": "auth failed"}
        })

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    with pytest.raises(MiniMaxImageError) as exc:
        generate_image(api_key="bad", prompt="p", client=client)
    assert exc.value.code == MiniMaxErrorCode.AUTH_FAILED
    assert call_count["n"] == 1


def test_generate_retries_on_500_http():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 2:
            return httpx.Response(500, json={"message": "server error"})
        return httpx.Response(200, json=_ok_response())

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    import shop_pipeline.clients.minimax_image_client as mod
    mod.time.sleep = lambda s: None
    result = generate_image(api_key="k", prompt="p", client=client)
    assert result.urls == ["https://cdn.minimaxi.com/img1.png"]
    assert call_count["n"] == 2


def test_is_retryable_classification():
    assert _is_retryable(MiniMaxErrorCode.RATE_LIMITED) is True
    assert _is_retryable(MiniMaxErrorCode.SERVER_ERROR) is True
    assert _is_retryable(MiniMaxErrorCode.AUTH_FAILED) is False
    assert _is_retryable(MiniMaxErrorCode.INSUFFICIENT_BALANCE) is False
    assert _is_retryable(MiniMaxErrorCode.SENSITIVE_CONTENT) is False
    assert _is_retryable(MiniMaxErrorCode.BAD_PARAMS) is False


def test_validate_aspect_ratio():
    """Aspect ratio must be in the supported set, otherwise ValueError."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    with pytest.raises(ValueError, match="Unsupported aspect ratio"):
        generate_image(api_key="k", prompt="p", aspect_ratio="5:5", client=client)


def test_validate_n_range():
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    client = httpx.Client(transport=transport, base_url="https://api.minimaxi.com")
    with pytest.raises(ValueError, match="n must be 1-9"):
        generate_image(api_key="k", prompt="p", n=10, client=client)
    with pytest.raises(ValueError, match="n must be 1-9"):
        generate_image(api_key="k", prompt="p", n=0, client=client)
