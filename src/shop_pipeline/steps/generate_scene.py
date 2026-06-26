"""Scene image generation step.

Combines DashScope client with prompt templates to produce multiple scene images.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from shop_pipeline.clients.dashscope_client import (
    ImageResult,
    generate_scene_image,
)
from shop_pipeline.logging_setup import get_logger
from shop_pipeline.prompts import get_scenes

log = get_logger("shop_pipeline.steps.generate_scene")


@dataclass(frozen=True)
class SceneOutput:
    """One generated scene image on disk."""

    name: str
    aspect_ratio: str
    image_path: Path


def _download_to(url: str, dst: Path, client: httpx.Client) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with dst.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)


def generate_scenes(
    api_key: str,
    product_image_path: Path,
    product_type: str,
    product_desc: str,
    out_dir: Path,
    on_progress: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> list[SceneOutput]:
    """Generate multiple scene images for a product.

    Args:
        api_key: DashScope API key
        product_image_path: local path to the product image (used as reference)
        product_type: clothing | electronics | food | other
        product_desc: short description of the product (used in prompts)
        out_dir: directory to save generated images
        on_progress: optional callback(scene_name) for UI progress
        client: optional httpx.Client (for testing)

    Returns:
        list of SceneOutput with local file paths

    Raises:
        ValueError: unknown product_type
        DashScopeError: API failure
    """
    scenes = get_scenes(product_type, product_desc)
    log.info("generating %d scenes for %s", len(scenes), product_type)
    out_dir.mkdir(parents=True, exist_ok=True)

    own_client = client is None
    http = client or httpx.Client(timeout=120.0)
    outputs: list[SceneOutput] = []
    try:
        for scene in scenes:
            if on_progress:
                on_progress(scene["name"])
            log.info("scene: %s (%s)", scene["name"], scene["aspect_ratio"])
            result: ImageResult = generate_scene_image(
                api_key=api_key,
                prompt=scene["prompt"],
                product_image_path=product_image_path,
                aspect_ratio=scene["aspect_ratio"],
                client=http,
            )
            out_path = out_dir / f"scene-{scene['name']}.png"
            _download_to(result.url, out_path, http)
            outputs.append(
                SceneOutput(
                    name=scene["name"],
                    aspect_ratio=scene["aspect_ratio"],
                    image_path=out_path,
                )
            )
            # Avoid hammering the API
            time.sleep(0.5)
    finally:
        if own_client:
            http.close()
    return outputs
