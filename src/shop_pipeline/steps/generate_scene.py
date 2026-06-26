"""Scene image generation step.

Provider-agnostic. Pass an image client (DashScope or MiniMax) and it will
generate multiple scene images for the product.

Public functions:
    generate_scenes_v2 — accepts a pre-selected client (preferred)
    generate_scenes   — legacy direct-DashScope (kept for back-compat)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from shop_pipeline.clients import ImageGenerationCall
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


def _extract_url(result: object) -> str:
    """Both DashScope and MiniMax results expose a single URL field."""
    url = getattr(result, "url", None)
    if url is not None:
        return url
    urls = getattr(result, "urls", None)
    if urls:
        return urls[0]
    raise RuntimeError(f"image result has no URL: {result!r}")


def generate_scenes(
    api_key: str,
    product_image_path: Path,
    product_type: str,
    product_desc: str,
    out_dir: Path,
    on_progress: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> list[SceneOutput]:
    """[Legacy] Generate scenes using DashScope directly.

    Kept for back-compat — new code should use generate_scenes_v2.

    The DashScope client is looked up at call time from its module so that
    tests can monkeypatch it.
    """
    import importlib

    ds_mod = importlib.import_module("shop_pipeline.clients.dashscope_client")
    return generate_scenes_v2(
        image_client=ds_mod.generate_scene_image,  # type: ignore[arg-type]
        api_key=api_key,
        product_image_path=product_image_path,
        product_type=product_type,
        product_desc=product_desc,
        out_dir=out_dir,
        on_progress=on_progress,
        client=client,
    )


def generate_scenes_v2(
    image_client: ImageGenerationCall,
    api_key: str,
    product_image_path: Path,
    product_type: str,
    product_desc: str,
    out_dir: Path,
    on_progress: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> list[SceneOutput]:
    """Generate multiple scene images using a pluggable image client.

    Args:
        image_client: callable matching ImageGenerationCall protocol
            (e.g. shop_pipeline.clients.dashscope_client.generate_scene_image
             or shop_pipeline.clients.minimax_image_client.generate_image)
        api_key: API key for the chosen provider
        product_image_path: local path to the product image (used as reference
            for providers that support it)
        product_type: clothing | electronics | food | other
        product_desc: short product description (used in prompts)
        out_dir: directory to save generated images
        on_progress: optional callback(scene_name) for UI progress
        client: optional httpx.Client (for testing)

    Returns:
        list of SceneOutput with local file paths
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
            # image_client protocols do not all accept `client`; check signature
            import inspect

            try:
                sig = inspect.signature(image_client)
                accepts_client = "client" in sig.parameters
            except (TypeError, ValueError):
                accepts_client = False
            kwargs = dict(
                api_key=api_key,
                prompt=scene["prompt"],
                product_image_path=product_image_path,
                aspect_ratio=scene["aspect_ratio"],
            )
            if accepts_client:
                kwargs["client"] = http
            result = image_client(**kwargs)
            url = _extract_url(result)
            out_path = out_dir / f"scene-{scene['name']}.png"
            _download_to(url, out_path, http)
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
