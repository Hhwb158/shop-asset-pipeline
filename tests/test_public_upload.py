"""Tests for the default public file upload (litterbox.catbox.moe)."""

from __future__ import annotations

import httpx
import pytest

from shop_pipeline.public_upload import (
    LitterboxError,
    upload_to_litterbox,
)


def test_upload_to_litterbox_returns_url():
    """Happy path: returns the public URL from the response body."""
    expected_url = "https://litter.catbox.moe/abc123.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "litterbox.catbox.moe":
            # Verify multipart upload contains the file
            assert "fileToUpload" in str(request.content)
            return httpx.Response(200, text=expected_url)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    # Write a tiny file to upload
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff\xe0fake jpeg")
        local = Path(f.name)

    try:
        url = upload_to_litterbox(local, expiry="1h", client=client)
        assert url == expected_url
    finally:
        local.unlink(missing_ok=True)


def test_upload_to_litterbox_invalid_expiry_raises(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="expiry must be one of"):
        upload_to_litterbox(p, expiry="1y", client=httpx.Client())


def test_upload_to_litterbox_missing_file_raises(tmp_path):
    missing = tmp_path / "no_such_file.jpg"
    with pytest.raises(FileNotFoundError):
        upload_to_litterbox(missing, client=httpx.Client())


def test_upload_to_litterbox_empty_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="   ")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"x")
        local = Path(f.name)
    try:
        with pytest.raises(LitterboxError, match="empty or invalid"):
            upload_to_litterbox(local, client=client)
    finally:
        local.unlink(missing_ok=True)


def test_upload_to_litterbox_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"x")
        local = Path(f.name)
    try:
        with pytest.raises(LitterboxError, match="500"):
            upload_to_litterbox(local, client=client)
    finally:
        local.unlink(missing_ok=True)


def test_upload_to_public_host_delegates_to_litterbox(monkeypatch):
    """The pipeline default upload_to_public_host should call upload_to_litterbox."""
    from shop_pipeline import public_upload

    calls: list[dict] = []

    def fake_litterbox(path, expiry="1h", client=None):
        calls.append({"path": path, "expiry": expiry})
        return "https://litter.catbox.moe/fake.jpg"

    monkeypatch.setattr(public_upload, "upload_to_litterbox", fake_litterbox)
    # Reimport pipeline to pick up the new default (or just call directly)
    from pathlib import Path

    url = public_upload.upload_to_public_host(Path("/tmp/x.jpg"))
    assert url == "https://litter.catbox.moe/fake.jpg"
    assert calls[0]["expiry"] == "1h"
