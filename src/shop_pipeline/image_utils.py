"""Shared image helpers for product assets."""

from __future__ import annotations

from PIL import Image


def fit_image_on_square_canvas(
    image: Image.Image,
    square_size: int = 1024,
    background: tuple[int, int, int] = (255, 255, 255),
    padding_ratio: float = 0.04,
) -> Image.Image:
    """Fit an image onto a square canvas without cropping or distortion."""
    if square_size <= 0:
        raise ValueError("square_size must be positive")
    if not 0 <= padding_ratio < 0.5:
        raise ValueError("padding_ratio must be between 0 and 0.5")

    source = image.convert("RGB")
    max_content = max(1, int(square_size * (1 - padding_ratio * 2)))
    scale = min(max_content / source.width, max_content / source.height)
    new_size = (
        max(1, round(source.width * scale)),
        max(1, round(source.height * scale)),
    )

    resized = source.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGB", (square_size, square_size), background)
    offset = ((square_size - new_size[0]) // 2, (square_size - new_size[1]) // 2)
    canvas.paste(resized, offset)
    return canvas
