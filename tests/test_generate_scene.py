"""Tests for scene generation step (mocked, provider-agnostic)."""

from __future__ import annotations

import httpx
import pytest
from PIL import Image

from shop_pipeline.steps.generate_scene import generate_scenes, generate_scenes_v2


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (1, 1), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -------- generate_scenes (legacy) --------


def test_generate_scenes_creates_files(tmp_path, monkeypatch):
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    out_dir = tmp_path / "scenes"

    image_bytes = _png_bytes()

    # Patch the DashScope client to return our URL without hitting network
    from shop_pipeline.clients import dashscope_client

    def fake_ds(**kwargs):
        class R:
            url = "https://cdn.test/scene.png"

        return R()

    monkeypatch.setattr(dashscope_client, "generate_scene_image", fake_ds)

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    progress: list[str] = []
    outputs = generate_scenes(
        api_key="k",
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        out_dir=out_dir,
        on_progress=progress.append,
        client=client,
    )
    assert len(outputs) == 4
    assert all(o.image_path.exists() for o in outputs)
    assert progress == ["studio-white", "outdoor-cafe", "lifestyle-indoor", "social-square"]


def test_generate_scenes_unknown_type_raises(tmp_path):
    product = tmp_path / "product.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(product)
    with pytest.raises(ValueError, match="Unknown product_type"):
        generate_scenes(
            api_key="k",
            product_image_path=product,
            product_type="spaceship",
            product_desc="rocket",
            out_dir=tmp_path / "out",
        )


# -------- generate_scenes_v2 (provider-agnostic) --------


def test_generate_scenes_v2_uses_provided_image_client(tmp_path):
    """v2: caller provides the image client (mock returns URL)."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    out_dir = tmp_path / "scenes"

    image_bytes = _png_bytes()
    call_log: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    def my_image_client(*, api_key, prompt, product_image_path, aspect_ratio):
        call_log.append(
            {"api_key": api_key, "prompt": prompt, "has_ref": product_image_path is not None}
        )

        class R:
            url = "https://cdn.test/scene.png"

        return R()

    outputs = generate_scenes_v2(
        image_client=my_image_client,
        api_key="test-key",
        product_image_path=product,
        product_type="clothing",
        product_desc="red t-shirt",
        out_dir=out_dir,
        client=client,
    )

    assert len(outputs) == 4
    assert all(o.image_path.exists() for o in outputs)
    # The injected client was called for every scene
    assert len(call_log) == 4
    assert all(c["api_key"] == "test-key" for c in call_log)
    assert all(c["has_ref"] for c in call_log)


def test_generate_scenes_v2_works_with_minimax_style_result(tmp_path):
    """v2 should also accept results with `urls` list (MiniMax shape)."""
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    out_dir = tmp_path / "scenes"
    image_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "cdn.test" in str(request.url):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    def minimax_style_client(*, api_key, prompt, product_image_path, aspect_ratio):
        url = "https://cdn.test/scene.png"

        class R:
            def __init__(self):
                self.urls = [url]

        return R()

    outputs = generate_scenes_v2(
        image_client=minimax_style_client,
        api_key="sk-cp-test",
        product_image_path=product,
        product_type="electronics",
        product_desc="black earbuds",
        out_dir=out_dir,
        client=client,
    )
    assert len(outputs) == 4
    assert all(o.image_path.exists() for o in outputs)
