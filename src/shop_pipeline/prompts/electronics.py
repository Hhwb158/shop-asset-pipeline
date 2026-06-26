"""Prompt templates for 3C / electronics products."""

from __future__ import annotations

SCENES: list[tuple[str, str, str]] = [
    (
        "studio-clean",
        "{product_desc} on a gradient gray studio backdrop, "
        "soft professional lighting, sharp focus, product photography",
        "1:1",
    ),
    (
        "desk-setup",
        "{product_desc} on a modern minimalist desk, "
        "laptop and notebook in the soft-focus background, natural daylight",
        "1:1",
    ),
    (
        "hand-held",
        "Close-up of a hand holding {product_desc}, "
        "lifestyle perspective, well-lit, showcasing scale",
        "1:1",
    ),
    (
        "tech-dark",
        "{product_desc} on a black surface with rim lighting, "
        "futuristic tech aesthetic, dramatic shadows",
        "1:1",
    ),
]


def build_scenes(product_desc: str) -> list[dict]:
    return [
        {"name": name, "prompt": prompt.format(product_desc=product_desc), "aspect_ratio": ar}
        for name, prompt, ar in SCENES
    ]
