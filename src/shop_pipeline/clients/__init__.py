"""API clients (thin wrappers, mock-friendly).

Public surface:
    ImageProvider        — enum of supported image providers
    ImageGenerationCall  — protocol every image client must satisfy
    get_image_client     — factory: pick a provider, get a client

Note: provider functions are looked up dynamically via module attribute, so
monkeypatching `shop_pipeline.clients.dashscope_client.generate_scene_image`
in tests will be picked up by the factory.
"""

from __future__ import annotations

import importlib
from enum import StrEnum
from typing import Protocol

from ..config import Config
from .dashscope_client import ImageResult as DashScopeImageResult

# Eager imports so callers can patch via module path
from .dashscope_client import generate_scene_image as dashscope_generate
from .minimax_image_client import ImageResult as MiniMaxImageResult
from .minimax_image_client import generate_image as minimax_generate_t2i
from .minimax_image_client import generate_image_with_subject as minimax_generate_i2i


class ImageProvider(StrEnum):
    """Which image generation backend to use for scene images."""

    DASHSCOPE = "dashscope"
    MINIMAX = "minimax"


class ImageGenerationCall(Protocol):
    """Protocol every image client must satisfy.

    Takes a prompt, optional reference image, aspect ratio; returns image URLs.
    Implementations: dashscope_generate, minimax_generate_t2i/i2i.
    """

    def __call__(
        self,
        *,
        api_key: str,
        prompt: str,
        product_image_path: object | None = None,
        aspect_ratio: str = "1:1",
    ) -> object: ...


def get_image_client(
    provider: ImageProvider,
    use_subject_reference: bool = False,
) -> ImageGenerationCall:
    """Return the image-generation function for the given provider.

    Looks up the function dynamically from its module so tests can
    monkeypatch the module attribute and have the change take effect.

    Args:
        provider: dashscope or minimax
        use_subject_reference: only relevant for minimax — when True, returns
            a function that accepts product_image_path and uses i2i endpoint.
            DashScope always supports reference images via its `ref_img` param.

    Returns:
        Callable with signature matching ImageGenerationCall
    """
    if provider == ImageProvider.DASHSCOPE:
        mod = importlib.import_module("shop_pipeline.clients.dashscope_client")
        return mod.generate_scene_image  # type: ignore[return-value]
    if provider == ImageProvider.MINIMAX:
        mod = importlib.import_module("shop_pipeline.clients.minimax_image_client")
        if use_subject_reference:
            return mod.generate_image_with_subject  # type: ignore[return-value]
        return mod.generate_image  # type: ignore[return-value]
    raise ValueError(f"Unknown provider: {provider}")


def provider_available(provider: ImageProvider, config: Config) -> bool:
    """Check if the provider's API key is configured."""
    if provider == ImageProvider.DASHSCOPE:
        return config.has_dashscope()
    if provider == ImageProvider.MINIMAX:
        return config.has_minimax()
    return False


def list_available_providers(config: Config) -> list[ImageProvider]:
    """Return the providers the user can actually use right now."""
    return [p for p in ImageProvider if provider_available(p, config)]


__all__ = [
    "DashScopeImageResult",
    "ImageGenerationCall",
    "ImageProvider",
    "MiniMaxImageResult",
    "dashscope_generate",
    "get_image_client",
    "list_available_providers",
    "minimax_generate_i2i",
    "minimax_generate_t2i",
    "provider_available",
]

