"""Kling AI (Kuaishou) image-to-video client.

Kling uses JWT-based auth: HS256 over `api_key.api_secret` with claims iss/exp/iat.
Video generation is async: POST creates a task, GET polls until succeeded/failed.

Note: Kling API has evolved (kling-v1, v1-5, v1-6). The default model and
endpoints here reflect the public docs as of late 2025. If the model is
renamed or the path changes, only this file needs updating.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "https://api.klingai.com"
IMAGE_TO_VIDEO_PATH = "/v1/videos/image2video"
TASK_QUERY_PATH = "/v1/videos/image2video/{task_id}"
DEFAULT_MODEL = "kling-v1-5"

# Polling
POLL_INTERVAL_S = 5.0
POLL_TIMEOUT_S = 300.0  # 5 minutes


class KlingError(RuntimeError):
    """Raised on Kling API error."""


class NotReady(Exception):
    """Raised when the video task is still processing."""

    def __init__(self, task_id: str, status: str):
        super().__init__(f"Task {task_id} still {status}")
        self.task_id = task_id
        self.status = status


@dataclass(frozen=True)
class VideoResult:
    """A finished video."""

    task_id: str
    video_url: str
    duration: str  # e.g. "5" (seconds)


def _make_jwt(api_key: str, api_secret: str) -> str:
    """Generate a Kling JWT.

    Kling uses HS256 with the API secret. The payload is the standard
    JWT (iss, iat, exp) where iss is the API key.
    """
    # Kling's exact algo: they publish a Python snippet using PyJWT directly
    # with HS256 and secret = api_secret. Header is {"alg": "HS256", "typ": "JWT"}.
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": api_key,
        "iat": now,
        "exp": now + 1800,  # 30 min validity
    }

    def b64(d: dict) -> str:
        import json

        s = json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(s).rstrip(b"=").decode("ascii")

    signing_input = f"{b64(header)}.{b64(payload)}".encode("ascii")
    signature = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{signing_input.decode('ascii')}.{sig_b64}"


def _post_json(client: httpx.Client, jwt: str, path: str, payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }
    resp = client.post(path, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise KlingError(f"Kling HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code", 0) != 0:
        raise KlingError(f"Kling API error: code={data.get('code')} msg={data.get('message')}")
    return data


def _get_json(client: httpx.Client, jwt: str, path: str) -> dict:
    headers = {"Authorization": f"Bearer {jwt}"}
    resp = client.get(path, headers=headers)
    if resp.status_code >= 400:
        raise KlingError(f"Kling HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code", 0) != 0:
        raise KlingError(f"Kling API error: code={data.get('code')} msg={data.get('message')}")
    return data


def image_to_video(
    api_key: str,
    api_secret: str,
    image_url: str,
    prompt: str,
    duration: int = 5,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> str:
    """Create an image-to-video task. Returns task_id (use poll_video_task to wait).

    Args:
        api_key: Kling AK
        api_secret: Kling SK
        image_url: URL of the source image (must be publicly accessible)
        prompt: text description of the desired motion
        duration: 5 or 10 seconds
        model: model name (default kling-v1-5)
        base_url: API base URL
        client: optional httpx.Client (for testing)

    Returns:
        task_id string
    """
    if not (api_key and api_secret):
        raise KlingError("api_key and api_secret are required")
    if duration not in (5, 10):
        raise ValueError(f"duration must be 5 or 10, got {duration}")

    payload = {
        "model_name": model,
        "prompt": prompt,
        "image": image_url,
        "duration": str(duration),
    }
    jwt = _make_jwt(api_key, api_secret)

    own_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60.0)
    try:
        data = _post_json(http, jwt, IMAGE_TO_VIDEO_PATH, payload)
    finally:
        if own_client:
            http.close()
    return data["data"]["task_id"]


def poll_video_task(
    api_key: str,
    api_secret: str,
    task_id: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = POLL_TIMEOUT_S,
    client: httpx.Client | None = None,
) -> VideoResult:
    """Poll a task until it completes.

    Returns:
        VideoResult on success

    Raises:
        NotReady: task still processing (caller can retry)
        KlingError: task failed
    """
    jwt = _make_jwt(api_key, api_secret)
    path = TASK_QUERY_PATH.format(task_id=task_id)
    own_client = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60.0)
    try:
        start = time.monotonic()
        while True:
            data = _get_json(http, jwt, path)
            task = data.get("data", {})
            status = task.get("task_status")
            if status == "succeed":
                videos = task.get("task_result", {}).get("videos") or []
                if not videos:
                    raise KlingError(f"Task {task_id} succeeded but no videos returned")
                v = videos[0]
                return VideoResult(
                    task_id=task_id,
                    video_url=v["url"],
                    duration=v.get("duration", "5"),
                )
            if status == "failed":
                raise KlingError(
                    f"Task {task_id} failed: {task.get('task_status_msg', 'unknown')}"
                )
            # status is "submitted" or "processing" — wait
            if time.monotonic() - start > timeout_s:
                raise KlingError(
                    f"Task {task_id} timed out after {timeout_s}s (status={status})"
                )
            raise NotReady(task_id, status or "unknown")
    finally:
        if own_client:
            http.close()
