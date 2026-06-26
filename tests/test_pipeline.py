"""Tests for top-level pipeline orchestration."""

from __future__ import annotations

import httpx
import pytest
from PIL import Image

from shop_pipeline.clients import ImageProvider, get_image_client, list_available_providers
from shop_pipeline.config import Config
from shop_pipeline.pipeline import run_pipeline


def _png_bytes(color=(200, 50, 50), size=(200, 200)) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_pipeline_white_bg_only_when_no_keys(tmp_path):
    """Without any API keys, pipeline still produces white-bg main image."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    cfg = Config(
        dashscope_api_key=None, kling_api_key=None,
        kling_api_secret=None, minimax_api_key=None,
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
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    # Patch the real DashScope image client (looked up dynamically by factory)
    from shop_pipeline.clients import dashscope_client

    def fake_ds(**kwargs):
        class R:
            url = "https://cdn.test/scene.png"

        return R()

    monkeypatch.setattr(dashscope_client, "generate_scene_image", fake_ds)

    cfg = Config(
        dashscope_api_key="ds",
        kling_api_key=None, kling_api_secret=None, minimax_api_key=None,
    )
    work = tmp_path / "out"

    result = run_pipeline(
        config=cfg,
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        work_dir=work,
        generate_video=False,
        scene_mode="background_only",  # i2i works with any provider in pipeline routing
        http_client=client,
    )
    assert result.white_bg_path.exists()
    assert len(result.scenes) == 4
    for s in result.scenes:
        assert s.image_path.exists()


def test_pipeline_with_minimax_generates_scenes(tmp_path, monkeypatch):
    """With MiniMax key, pipeline routes through MiniMax client."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)

    image_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    from shop_pipeline.clients import minimax_image_client as mm

    def fake_mm_i2i(**kwargs):
        url = "https://cdn.test/scene.png"

        class R:
            def __init__(self):
                self.urls = [url]

        return R()

    monkeypatch.setattr(mm, "generate_image_with_subject", fake_mm_i2i)
    monkeypatch.setattr(mm, "generate_image", fake_mm_i2i)

    cfg = Config(
        dashscope_api_key=None,
        kling_api_key=None, kling_api_secret=None, minimax_api_key="sk-cp-test",
    )
    work = tmp_path / "out"

    result = run_pipeline(
        config=cfg,
        product_image_path=product,
        product_type="electronics",
        product_desc="black earbuds",
        work_dir=work,
        generate_video=False,
        scene_mode="background_only",
        http_client=client,
    )
    assert result.white_bg_path.exists()
    assert len(result.scenes) == 4
    for s in result.scenes:
        assert s.image_path.exists()


def test_pipeline_auto_selects_provider_when_unset(tmp_path, monkeypatch):
    """When image_provider is None, pipeline picks the first available one."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)

    image_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    from shop_pipeline.clients import dashscope_client

    def fake(**kwargs):
        class R:
            url = "https://cdn.test/scene.png"

        return R()

    monkeypatch.setattr(dashscope_client, "generate_scene_image", fake)

    cfg = Config(
        dashscope_api_key="ds",  # only dashscope available
        kling_api_key=None, kling_api_secret=None, minimax_api_key=None,
    )
    work = tmp_path / "out"

    result = run_pipeline(
        config=cfg,
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        work_dir=work,
        generate_video=False,
        scene_mode="background_only",
        http_client=client,
    )
    assert len(result.scenes) == 4


# -------- provider registry --------


def test_list_available_providers_filters_by_keys():
    cfg_full = Config(
        dashscope_api_key="d", kling_api_key="k", kling_api_secret="s", minimax_api_key="m"
    )
    assert ImageProvider.DASHSCOPE in list_available_providers(cfg_full)
    assert ImageProvider.MINIMAX in list_available_providers(cfg_full)

    cfg_mm_only = Config(
        dashscope_api_key=None, kling_api_key=None, kling_api_secret=None, minimax_api_key="m"
    )
    assert list_available_providers(cfg_mm_only) == [ImageProvider.MINIMAX]

    cfg_empty = Config(
        dashscope_api_key=None, kling_api_key=None, kling_api_secret=None, minimax_api_key=None
    )
    assert list_available_providers(cfg_empty) == []


def test_get_image_client_returns_correct_callable():
    fn = get_image_client(ImageProvider.DASHSCOPE, use_subject_reference=False)
    assert callable(fn)
    fn2 = get_image_client(ImageProvider.MINIMAX, use_subject_reference=True)
    assert callable(fn2)
    fn3 = get_image_client(ImageProvider.MINIMAX, use_subject_reference=False)
    # t2i and i2i are different functions
    assert fn2 is not fn3


def test_get_image_client_unknown_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_image_client("bogus")  # type: ignore[arg-type]
