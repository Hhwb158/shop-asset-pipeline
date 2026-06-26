"""MiniMax (Xiyu Technology) image generation client.

POST https://api.minimaxi.com/v1/image_generation
Auth: Bearer <MINIMAX_API_KEY>
Models: image-01 (default), image-01-live (with style)
Reference: https://platform.minimaxi.com/docs/api-reference/image-generation-t2i
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.minimaxi.com"
GENERATION_PATH = "/v1/image_generation"
DEFAULT_MODEL = "image-01"
LIVE_MODEL = "image-01-live"

# Aspect ratios supported by MiniMax (8 options)
SUPPORTED_ASPECTS: tuple[str, ...] = (
    "1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9",
)

MAX_PROMPT_LEN = 1500
N_MIN, N_MAX = 1, 9
MAX_RETRIES = 2
RETRY_BACKOFF_S = 1.5


class MiniMaxErrorCode(IntEnum):
    """MiniMax API error codes (subset we handle)."""

    SUCCESS = 0
    RATE_LIMITED = 1002
    AUTH_FAILED = 1004
    INSUFFICIENT_BALANCE = 1008
    SENSITIVE_CONTENT = 1026
    BAD_PARAMS = 2013
    INVALID_API_KEY = 2049
    SERVER_ERROR = 500  # HTTP-level


class MiniMaxImageError(RuntimeError):
    """Raised on MiniMax API error. Carries structured code for UI handling."""

    def __init__(self, message: str, code: MiniMaxErrorCode):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImageResult:
    """Result of an image generation call."""

    urls: list[str]
    task_id: str
    success_count: int
    failed_count: int


def _validate_aspect(aspect: str) -> None:
    if aspect not in SUPPORTED_ASPECTS:
        raise ValueError(
            f"Unsupported aspect ratio: {aspect}. "
            f"Use one of: {', '.join(SUPPORTED_ASPECTS)}"
        )


def _validate_n(n: int) -> None:
    if not (N_MIN <= n <= N_MAX):
        raise ValueError(f"n must be {N_MIN}-{N_MAX}, got {n}")


def _validate_prompt(prompt: str) -> None:
    if not prompt:
        raise ValueError("prompt is required")
    if len(prompt) > MAX_PROMPT_LEN:
        raise ValueError(f"prompt too long: {len(prompt)} > {MAX_PROMPT_LEN}")


def _is_retryable(code: MiniMaxErrorCode) -> bool:
    return code in (MiniMaxErrorCode.RATE_LIMITED, MiniMaxErrorCode.SERVER_ERROR)


def _request(
    client: httpx.Client,
    api_key: str,
    payload: dict,
) -> dict:
    """POST with retry on rate-limit (1002) and HTTP 5xx."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.post(GENERATION_PATH, headers=headers, json=payload)
            if 500 <= resp.status_code < 600:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                    continue
                raise MiniMaxImageError(
                    f"MiniMax server error {resp.status_code}: {resp.text[:200]}",
                    code=MiniMaxErrorCode.SERVER_ERROR,
                )
            if resp.status_code >= 400:
                raise MiniMaxImageError(
                    f"MiniMax HTTP {resp.status_code}: {resp.text[:200]}",
                    code=MiniMaxErrorCode.BAD_PARAMS,
                )
            data = resp.json()
        except httpx.RequestError as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise MiniMaxImageError(
                f"MiniMax network error: {e}",
                code=MiniMaxErrorCode.SERVER_ERROR,
            ) from e

        # API-level error
        base_resp = data.get("base_resp", {})
        code_int = int(base_resp.get("status_code", 0))
        if code_int != 0:
            try:
                code = MiniMaxErrorCode(code_int)
            except ValueError:
                code = MiniMaxErrorCode.BAD_PARAMS
            msg = base_resp.get("status_msg", "unknown error")
            if _is_retryable(code) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise MiniMaxImageError(
                f"MiniMax API error {code_int} ({code.name}): {msg}",
                code=code,
            )
        return data
    # Exhausted retries
    raise MiniMaxImageError(
        f"MiniMax failed after retries: {last_exc}",
        code=MiniMaxErrorCode.SERVER_ERROR,
    )


def _build_result(data: dict) -> ImageResult:
    payload = data.get("data", {})
    urls = payload.get("image_urls") or []
    if not urls:
        # Only fall back to base64 if explicitly requested; in URL mode this is an error
        b64 = payload.get("image_base64") or []
        if b64:
            urls = [f"data:image/jpeg;base64,{b}" for b in b64]
    if not urls:
        raise MiniMaxImageError("MiniMax returned no images", code=MiniMaxErrorCode.SUCCESS)
    meta = data.get("metadata", {})
    return ImageResult(
        urls=urls,
        task_id=data.get("id", ""),
        success_count=int(meta.get("success_count", len(urls))),
        failed_count=int(meta.get("failed_count", 0)),
    )


def generate_image(
    api_key: str,
    prompt: str,
    aspect_ratio: str = "1:1",
    n: int = 1,
    model: str = DEFAULT_MODEL,
    response_format: str = "url",
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> ImageResult:
    """Text-to-image via MiniMax.

    Args:
        api_key: MiniMax API key (sk-cp-...)
        prompt: text description (≤ 1500 chars)
        aspect_ratio: one of SUPPORTED_ASPECTS
        n: number of images (1-9)
        model: "image-01" or "image-01-live"
        response_format: "url" (24h) or "base64"
        base_url: API base URL
        client: optional httpx.Client (for testing)

    Returns:
        ImageResult with list of image URLs
    """
    if not api_key:
        raise MiniMaxImageError("api_key is required", code=MiniMaxErrorCode.AUTH_FAILED)
    _validate_prompt(prompt)
    _validate_aspect(aspect_ratio)
    _validate_n(n)

    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": n,
        "response_format": response_format,
    }

    own_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60.0)
    try:
        data = _request(http, api_key, payload)
        return _build_result(data)
    finally:
        if own_client:
            http.close()


def generate_image_with_subject(
    api_key: str,
    prompt: str,
    product_image_path: str | Path | None = None,
    *,
    subject_image_url: str | None = None,
    subject_type: str = "character",
    aspect_ratio: str = "1:1",
    n: int = 1,
    model: str = DEFAULT_MODEL,
    response_format: str = "url",
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> ImageResult:
    """Image-to-image with a single subject reference (preserves identity).

    Accepts either `product_image_path` (local file path — used in pipelines)
    or `subject_image_url` (public URL — used in unit tests / direct calls).
    The local file is uploaded to a temporary public URL first; for tests,
    prefer passing subject_image_url directly.

    Args:
        api_key: MiniMax API key
        prompt: text description (≤ 1500 chars)
        product_image_path: local file path of the reference image
        subject_image_url: publicly accessible URL of the reference image
        subject_type: "character" (only one supported currently)
        (other args same as generate_image)
    """
    if subject_image_url is None and product_image_path is not None:
        # In production this would upload the local file to a CDN first.
        # For now we expect callers to provide a public URL.
        raise MiniMaxImageError(
            "Local product_image_path not supported yet. "
            "Upload the file to a CDN and pass subject_image_url.",
            code=MiniMaxErrorCode.BAD_PARAMS,
        )
    if not subject_image_url:
        raise MiniMaxImageError(
            "subject_image_url is required", code=MiniMaxErrorCode.BAD_PARAMS
        )

    _validate_prompt(prompt)
    _validate_aspect(aspect_ratio)
    _validate_n(n)

    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": n,
        "response_format": response_format,
        "subject_reference": [
            {"type": subject_type, "image_file": subject_image_url},
        ],
    }

    own_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60.0)
    try:
        data = _request(http, api_key, payload)
        return _build_result(data)
    finally:
        if own_client:
            http.close()
