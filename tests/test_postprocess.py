"""Tests for postprocess (ffmpeg) step."""

from __future__ import annotations

import pytest

from shop_pipeline.steps.postprocess import (
    add_subtitle_to_video,
    check_ffmpeg_available,
)


def test_check_ffmpeg_available_returns_bool():
    """Just a smoke test — ffmpeg may or may not be installed."""
    result = check_ffmpeg_available()
    assert isinstance(result, bool)


def test_add_subtitle_raises_if_ffmpeg_missing(monkeypatch, tmp_path):
    """When ffmpeg is not on PATH, FFmpegError is raised."""
    from shop_pipeline.steps import postprocess

    monkeypatch.setattr(postprocess, "check_ffmpeg_available", lambda: False)

    src = tmp_path / "src.mp4"
    src.write_bytes(b"not a real video, but file exists")
    dst = tmp_path / "dst.mp4"

    with pytest.raises(Exception, match="ffmpeg"):
        add_subtitle_to_video(src, dst, "hello")


def test_add_subtitle_raises_if_src_missing(monkeypatch, tmp_path):
    from shop_pipeline.steps import postprocess

    monkeypatch.setattr(postprocess, "check_ffmpeg_available", lambda: True)

    with pytest.raises(FileNotFoundError):
        add_subtitle_to_video(tmp_path / "nope.mp4", tmp_path / "dst.mp4", "x")
