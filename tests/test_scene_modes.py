"""Tests for scene mode validation and routing."""

from __future__ import annotations

import pytest

from shop_pipeline.scene_modes import (
    MODE_DESCRIPTIONS,
    SceneMode,
    SceneModeError,
    validate_scene_mode,
)

# -------- validate_scene_mode --------


def test_skip_mode_always_allowed():
    validate_scene_mode(SceneMode.SKIP, has_minimax_key=False, has_dashscope_key=False)
    validate_scene_mode(SceneMode.SKIP, has_minimax_key=True, has_dashscope_key=False)


def test_t2i_mode_always_rejected_with_clear_message():
    with pytest.raises(SceneModeError, match=r"t2i.*已禁用"):
        validate_scene_mode(SceneMode.T2I, has_minimax_key=True, has_dashscope_key=True)


def test_i2i_requires_minimax_key():
    with pytest.raises(SceneModeError, match="MiniMax API key"):
        validate_scene_mode(SceneMode.I2I, has_minimax_key=False, has_dashscope_key=True)


def test_i2i_works_with_minimax_key():
    validate_scene_mode(SceneMode.I2I, has_minimax_key=True, has_dashscope_key=False)
    validate_scene_mode(SceneMode.I2I, has_minimax_key=True, has_dashscope_key=True)


def test_background_only_requires_any_key():
    with pytest.raises(SceneModeError, match="至少一个图像生成 API key"):
        validate_scene_mode(
            SceneMode.BACKGROUND_ONLY, has_minimax_key=False, has_dashscope_key=False
        )


def test_background_only_works_with_either_key():
    validate_scene_mode(
        SceneMode.BACKGROUND_ONLY, has_minimax_key=True, has_dashscope_key=False
    )
    validate_scene_mode(
        SceneMode.BACKGROUND_ONLY, has_minimax_key=False, has_dashscope_key=True
    )


def test_composite_requires_any_key():
    with pytest.raises(SceneModeError, match="至少一个图像生成 API key"):
        validate_scene_mode(
            SceneMode.COMPOSITE, has_minimax_key=False, has_dashscope_key=False
        )


def test_mode_descriptions_cover_all_modes():
    for mode in SceneMode:
        assert mode in MODE_DESCRIPTIONS
        assert MODE_DESCRIPTIONS[mode]  # non-empty


def test_scene_mode_is_string_enum():
    """SceneMode can be used as a string (for serialization)."""
    assert SceneMode.I2I.value == "i2i"
    assert SceneMode.SKIP.value == "skip"
    assert SceneMode.T2I.value == "t2i"
    # StrEnum: str(member) returns the value, not the qualified name
    assert str(SceneMode.I2I) == "i2i"
