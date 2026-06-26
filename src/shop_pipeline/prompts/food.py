"""Prompt templates for food / daily goods products."""

from __future__ import annotations

SCENES: list[tuple[str, str, str]] = [
    (
        "table-spread",
        "{product_desc} on a rustic wooden table, "
        "surrounded by complementary ingredients, warm kitchen lighting, overhead angle",
        "1:1",
    ),
    (
        "hand-held-outdoor",
        "Hand holding {product_desc} outdoors in a park, "
        "natural sunlight, lifestyle photography, authentic feel",
        "1:1",
    ),
    (
        "kitchen-context",
        "{product_desc} in a bright modern kitchen, "
        "clean white surfaces, food photography style, appetizing",
        "1:1",
    ),
    (
        "social-vibrant",
        "{product_desc} with colorful props and bokeh, "
        "energetic social media aesthetic, vivid colors",
        "1:1",
    ),
]


def build_scenes(product_desc: str) -> list[dict]:
    return [
        {"name": name, "prompt": prompt.format(product_desc=product_desc), "aspect_ratio": ar}
        for name, prompt, ar in SCENES
    ]
