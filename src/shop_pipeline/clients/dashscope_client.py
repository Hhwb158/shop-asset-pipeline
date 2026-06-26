"""Alibaba DashScope image generation client.

Thin wrapper over DashScope's HTTP API. Mock-friendly (takes an httpx client).
Reference: https://help.aliyun.com/zh/model-studio/

Note: DashScope image-generation endpoint and exact model names can change.
       The default `qwen-image-plus` and the path below reflect the public docs
       as of late 2025. If the model is renamed or the endpoint moves, only
       this file needs updating.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_MODEL = "qwen-image-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
IMAGE_SYNTHESIS_PATH = "/api/v1/services/aigc/text2image/image-synthesis"

# Aspect ratio → "WxH" string DashScope accepts
ASPECT_TO_SIZE: dict[str, str] = {
    "1:1": "1024*1024",
    "3:4": "768*1024",
    "4:3": "1024*768",
    "9:16": "720*1280",
    "16:9": "1280*720",
}

MAX_RETRIES = 2  # 1 initial + 2 retries = 3 total attempts
RETRY_BACKOFF_S = 1.0


class DashScopeError(RuntimeError):
    """Raised when the DashScope API returns an error or no images."""


@dataclass(frozen=True)
class ImageResult:
    """A single image returned by the API."""

    url: str
    task_id: str


def _aspect_to_size(aspect: str) -> str:
    if aspect not in ASPECT_TO_SIZE:
        raise ValueError(
            f"Unsupported aspect ratio: {aspect}. "
            f"Use one of: {', '.join(ASPECT_TO_SIZE)}"
        )
    return ASPECT_TO_SIZE[aspect]


def _file_to_data_url(path: Path) -> str:
    """Read a local file and encode as data URL for API upload."""
    if not path.exists():
        raise FileNotFoundError(f"Reference image not found: {path}")
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "webp": "webp",
        "heic": "heic",
    }.get(suffix, "jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def _request_json(client: httpx.Client, headers: dict, payload: dict) -> dict[str, Any]:
    """POST with retry on 5xx."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.post(IMAGE_SYNTHESIS_PATH, headers=headers, json=payload)
            if 500 <= resp.status_code < 600:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                    continue
                raise DashScopeError(
                    f"DashScope server error {resp.status_code}: {resp.text}"
                )
            if resp.status_code >= 400:
                raise DashScopeError(
                    f"DashScope client error {resp.status_code}: {resp.text}"
                )
            return resp.json()
        except httpx.RequestError as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise DashScopeError(f"DashScope network error: {e}") from e
    raise DashScopeError(f"DashScope failed after retries: {last_exc}")


def generate_scene_image(
    api_key: str,
    prompt: str,
    product_image_path: Path | None = None,
    aspect_ratio: str = "1:1",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> ImageResult:
    """Generate a scene image via DashScope.

    Args:
        api_key: DashScope API key
        prompt: text description of the desired scene
        product_image_path: optional reference product image (local file)
        aspect_ratio: one of "1:1", "3:4", "4:3", "9:16", "16:9"
        model: model name (default qwen-image-plus)
        base_url: API base URL (override for testing)
        client: optional httpx.Client (for testing with MockTransport)

    Returns:
        ImageResult with URL and task_id

    Raises:
        DashScopeError: on API error, network failure, or no images returned
        ValueError: on invalid aspect ratio
    """
    if not api_key:
        raise DashScopeError("api_key is required")

    size = _aspect_to_size(aspect_ratio)
    parameters: dict[str, Any] = {"size": size, "n": 1}
    if product_image_path is not None:
        parameters["ref_img"] = _file_to_data_url(product_image_path)

    payload = {
        "model": model,
        "input": {"prompt": prompt, "parameters": parameters},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    own_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60.0)
    try:
        data = _request_json(http, headers, payload)
    finally:
        if own_client:
            http.close()

    results = data.get("output", {}).get("results") or []
    if not results:
        raise DashScopeError(f"DashScope returned no images: {data}")

    return ImageResult(
        url=results[0]["url"],
        task_id=data.get("output", {}).get("task_id", ""),
    )
