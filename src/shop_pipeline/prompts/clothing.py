"""Prompt templates for clothing / apparel products."""

from __future__ import annotations

# Each scene = (name, prompt_template, aspect_ratio)
# {product_desc} will be replaced by the user-provided description.

SCENES: list[tuple[str, str, str]] = [
    (
        "studio-white",
        "{product_desc} on a clean photography studio background, "
        "soft even lighting, product centered, high detail, e-commerce style",
        "1:1",
    ),
    (
        "outdoor-cafe",
        "{product_desc} placed on a wooden cafe table, morning sunlight, "
        "shallow depth of field, warm tones, lifestyle photography",
        "3:4",
    ),
    (
        "lifestyle-indoor",
        "{product_desc} in a cozy modern living room, natural light from window, "
        "soft shadows, aspirational lifestyle, magazine style",
        "4:3",
    ),
    (
        "social-square",
        "{product_desc} with vibrant bokeh background, trendy social media aesthetic, "
        "punchy colors, eye-catching composition",
        "1:1",
    ),
]


def build_scenes(product_desc: str) -> list[dict]:
    """Return scene configs ready for the DashScope client."""
    return [
        {"name": name, "prompt": prompt.format(product_desc=product_desc), "aspect_ratio": ar}
        for name, prompt, ar in SCENES
    ]
