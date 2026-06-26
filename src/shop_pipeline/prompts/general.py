"""Generic prompt templates — used when product type is 'other'."""

from __future__ import annotations

SCENES: list[tuple[str, str, str]] = [
    (
        "studio-clean",
        "{product_desc} on a clean white studio background, "
        "soft professional lighting, centered composition, e-commerce style",
        "1:1",
    ),
    (
        "lifestyle-soft",
        "{product_desc} in a softly lit lifestyle setting, "
        "warm tones, shallow depth of field, natural composition",
        "3:4",
    ),
    (
        "context-bright",
        "{product_desc} in a bright, airy room, "
        "natural light, aspirational mood, magazine quality",
        "16:9",
    ),
    (
        "social-vibrant",
        "{product_desc} with vibrant bokeh background, "
        "eye-catching composition, social media aesthetic",
        "1:1",
    ),
]


def build_scenes(product_desc: str) -> list[dict]:
    return [
        {"name": name, "prompt": prompt.format(product_desc=product_desc), "aspect_ratio": ar}
        for name, prompt, ar in SCENES
    ]
