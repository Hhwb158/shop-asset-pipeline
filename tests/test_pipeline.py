"""Tests for top-level pipeline orchestration."""

from __future__ import annotations

import httpx
from PIL import Image

from shop_pipeline.config import Config
from shop_pipeline.pipeline import run_pipeline


def _png_bytes(color=(200, 50, 50), size=(200, 200)) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _make_config(dashscope: str = "ds", kling_key: str = "ak", kling_secret: str = "sk") -> Config:
    return Config(
        dashscope_api_key=dashscope,
        kling_api_key=kling_key,
        kling_api_secret=kling_secret,
    )


def test_pipeline_white_bg_only_when_no_keys(tmp_path):
    """Without any API keys, pipeline still produces white-bg main image."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    cfg = Config(
        dashscope_api_key=None, kling_api_key=None, kling_api_secret=None
    )
    work = tmp_path / "out"

    result = run_pipeline(
        config=cfg,
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        work_dir=work,
        generate_video=False,
    )

    assert result.white_bg_path.exists()
    assert result.scenes == []
    assert result.video is None


def test_pipeline_with_dashscope_generates_scenes(tmp_path, monkeypatch):
    """With DashScope key, pipeline generates 4 scene images."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)

    image_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"output": {"task_id": "t1", "results": [{"url": "https://cdn/scene.png"}]}},
            )
        if request.url.path.endswith("/scene.png"):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    httpx.Client(transport=transport, base_url="https://dashscope.aliyuncs.com")

    # Monkey-patch the DashScope client used inside generate_scene to use our mock
    from shop_pipeline.steps import generate_scene as gs

    monkeypatch.setattr(gs, "generate_scene_image", lambda **kwargs: kwargs["api_key"] and __import__(
        "shop_pipeline.clients.dashscope_client", fromlist=["ImageResult"]
    ).ImageResult(url="https://cdn/scene.png", task_id="t1"))

    # Patch _download_to to use our mock

    monkeypatch.setattr(gs, "_download_to", lambda url, dst, c: dst.write_bytes(image_bytes))

    cfg = _make_config()
    work = tmp_path / "out"

    result = run_pipeline(
        config=cfg,
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        work_dir=work,
        generate_video=False,
    )
    assert result.white_bg_path.exists()
    # Scenes will be 4 (clothing template)
    assert len(result.scenes) == 4
    for s in result.scenes:
        assert s.image_path.exists()
