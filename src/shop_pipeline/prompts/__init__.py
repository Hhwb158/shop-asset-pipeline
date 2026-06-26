"""Prompt template registry."""

from __future__ import annotations

from . import clothing, electronics, food, general

PRODUCT_TYPES = {
    "clothing": clothing,
    "electronics": electronics,
    "food": food,
    "other": general,
}


def get_scenes(product_type: str, product_desc: str) -> list[dict]:
    """Return scene configs for the given product type and description.

    Raises:
        ValueError: if product_type is unknown
    """
    if product_type not in PRODUCT_TYPES:
        raise ValueError(
            f"Unknown product_type: {product_type}. "
            f"Use one of: {', '.join(PRODUCT_TYPES)}"
        )
    return PRODUCT_TYPES[product_type].build_scenes(product_desc)
