"""Public file upload — default implementation uses litterbox.catbox.moe.

Litterbox is a free, anonymous, no-account-required temporary file host
(operated by catbox.moe). Files expire after 1h / 12h / 24h / 72h.

For production, override `upload_to_public_host` to use your CDN/OSS/S3.

This module is intentionally separate from the pipeline orchestration so
that:
  - tests can mock it easily
  - swapping backends is a one-line change in pipeline.py
"""

from __future__ import annotations

from pathlib import Path

import httpx

LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
VALID_EXPIRIES = ("1h", "12h", "24h", "72h")

DEFAULT_EXPIRY = "1h"
DEFAULT_TIMEOUT_S = 30.0


class LitterboxError(RuntimeError):
    """Raised when litterbox upload fails."""


def upload_to_litterbox(
    local_path: Path,
    expiry: str = DEFAULT_EXPIRY,
    base_url: str = LITTERBOX_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    client: httpx.Client | None = None,
) -> str:
    """Upload a local file to litterbox.catbox.moe and return its public URL.

    Args:
        local_path: file to upload
        expiry: one of "1h", "12h", "24h", "72h"
        base_url: override for testing
        timeout_s: HTTP timeout
        client: optional httpx.Client (for testing with MockTransport)

    Returns:
        Public URL (e.g. "https://litter.catbox.moe/abc.jpg")

    Raises:
        FileNotFoundError: local_path does not exist
        ValueError: expiry is not in VALID_EXPIRIES
        LitterboxError: upload failed or response was empty
    """
    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")
    if expiry not in VALID_EXPIRIES:
        raise ValueError(
            f"expiry must be one of {VALID_EXPIRIES}, got {expiry!r}"
        )

    own_client = client is None
    http = client or httpx.Client(timeout=timeout_s)
    try:
        with local_path.open("rb") as f:
            resp = http.post(
                base_url,
                data={"reqtype": "fileupload", "time": expiry},
                files={"fileToUpload": (local_path.name, f)},
            )
        if resp.status_code >= 400:
            raise LitterboxError(
                f"litterbox upload failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        url = resp.text.strip()
        if not url or not url.startswith("http"):
            raise LitterboxError(
                f"litterbox returned empty or invalid response: {resp.text!r}"
            )
        return url
    finally:
        if own_client:
            http.close()


def upload_to_public_host(
    local_path: Path,
    expiry: str = DEFAULT_EXPIRY,
) -> str:
    """Default implementation of the public-upload hook for the pipeline.

    Used by pipeline.run_pipeline to obtain a public URL for a local image
    (needed by MiniMax i2i / Kling video, which require public URLs).

    For production, override this with your CDN/OSS/S3 uploader.
    """
    return upload_to_litterbox(local_path, expiry=expiry)
