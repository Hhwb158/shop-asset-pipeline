"""Tests for scene generation step (mocked)."""

from __future__ import annotations

import httpx
import pytest
from PIL import Image

from shop_pipeline.steps.generate_scene import generate_scenes


def _mock_image_bytes() -> bytes:
    """Return bytes of a minimal valid PNG (1x1 white)."""
    from io import BytesIO

    img = Image.new("RGB", (1, 1), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_generate_scenes_creates_files(tmp_path):
    product = tmp_path / "product.png"
    Image.new("RGB", (200, 200), (200, 50, 50)).save(product)
    out_dir = tmp_path / "scenes"

    image_bytes = _mock_image_bytes()
    image_url = "https://cdn.example.com/scene.png"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"output": {"task_id": "t1", "results": [{"url": image_url}]}},
            )
        # GET for image download — match by URL path
        if request.url.path.endswith("/scene.png"):
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport, base_url="https://dashscope.aliyuncs.com"
    )

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

    # 4 scenes for clothing
    assert len(outputs) == 4
    assert all(o.image_path.exists() for o in outputs)
    assert progress == ["studio-white", "outdoor-cafe", "lifestyle-indoor", "social-square"]
    # Verify downloaded file is a valid PNG
    img = Image.open(outputs[0].image_path)
    assert img.size == (1, 1)


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
