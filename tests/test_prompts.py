"""Tests for prompt templates."""

from __future__ import annotations

import pytest

from shop_pipeline.prompts import PRODUCT_TYPES, get_scenes


def test_get_scenes_clothing_returns_four_scenes():
    scenes = get_scenes("clothing", "red cotton t-shirt")
    assert len(scenes) == 4
    for s in scenes:
        assert "name" in s
        assert "prompt" in s
        assert "aspect_ratio" in s
        assert "red cotton t-shirt" in s["prompt"]


def test_get_scenes_electronics_has_desk_scene():
    scenes = get_scenes("electronics", "black wireless earbuds")
    names = {s["name"] for s in scenes}
    assert "desk-setup" in names


def test_get_senes_food_has_table_scene():
    scenes = get_scenes("food", "artisan honey jar")
    names = {s["name"] for s in scenes}
    assert "table-spread" in names


def test_get_scenes_other_uses_general():
    scenes = get_scenes("other", "ceramic vase")
    assert len(scenes) == 4


def test_get_scenes_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown product_type"):
        get_scenes("spaceship", "rocket")


def test_all_product_types_have_same_scene_count():
    """Consistency: all types produce 4 scenes (uniform UI affordance)."""
    for ptype in PRODUCT_TYPES:
        scenes = get_scenes(ptype, "x")
        assert len(scenes) == 4, f"{ptype} has {len(scenes)} scenes"


def test_all_scene_prompts_are_square_product_images():
    for ptype in PRODUCT_TYPES:
        scenes = get_scenes(ptype, "x")
        assert {scene["aspect_ratio"] for scene in scenes} == {"1:1"}
