"""Scene generation modes and validation.

We MUST NOT produce images that look like product shots unless they
actually contain the user's product. Text-to-image ("t2i") models
generate plausible-looking but fabricated product photos when given
a generic prompt — these are misleading for e-commerce and were the
root cause of earlier issues in this project.

The four modes:

    SceneMode.SKIP
        Do not generate any scene images. Just the white-bg main image.

    SceneMode.I2I
        Image-to-image with the user's product as subject reference.
        Requires a public URL for the product image (uploaded via
        public_upload.upload_to_public_host). Produces scenes that
        actually contain the user's product.

    SceneMode.BACKGROUND_ONLY
        Generate scene backgrounds (no product in foreground). User
        composites the white-bg product themselves in post. Useful
        for designers who want artistic control.

    SceneMode.COMPOSITE
        (Future) Generate a scene background and composite the user's
        white-bg product onto it locally. The result is a real
        product placed in a real scene, not a fabricated one.

    SceneMode.T2I (DEPRECATED — disabled)
        Pure text-to-image. Disabled because it produces fake product
        images that mislead users. Retained as a name only so legacy
        callers get a clear error.
"""

from __future__ import annotations

from enum import StrEnum


class SceneMode(StrEnum):
    """How scene images should be produced."""

    SKIP = "skip"
    I2I = "i2i"
    BACKGROUND_ONLY = "background_only"
    COMPOSITE = "composite"
    T2I = "t2i"  # DEPRECATED, will raise SceneModeError


class SceneModeError(RuntimeError):
    """Raised when a scene mode cannot be applied (misconfigured, disabled, etc.)."""


# Maps modes to a human-readable explanation of what it does
MODE_DESCRIPTIONS: dict[SceneMode, str] = {
    SceneMode.SKIP: "不生成场景图,只输出白底主图",
    SceneMode.I2I: "i2i: 用产品图作为参考,生成保留产品外形的场景图(需公网 URL)",
    SceneMode.BACKGROUND_ONLY: "仅生成场景背景(不含产品),用户后期自己合成",
    SceneMode.COMPOSITE: "生成场景背景 + 自动合成白底产品图(本地 PIL)",
    SceneMode.T2I: "[已禁用] 纯文生图会产生伪造产品图,会误导用户",
}


def validate_scene_mode(mode: SceneMode, *, has_minimax_key: bool, has_dashscope_key: bool) -> None:
    """Raise SceneModeError if the mode cannot be applied right now.

    Rules:
        - SKIP: always allowed
        - I2I: requires MiniMax key (MiniMax is the only provider with
          a confirmed i2i subject-reference API today)
        - BACKGROUND_ONLY: requires either provider
        - COMPOSITE: requires either provider (background), no API needed
          for the composite step itself
        - T2I: always rejected with a clear message

    Args:
        mode: requested mode
        has_minimax_key: MiniMax API key present
        has_dashscope_key: DashScope API key present

    Raises:
        SceneModeError: if the mode cannot be applied
    """
    if mode == SceneMode.T2I:
        raise SceneModeError(
            "纯文生图(t2i)模式已禁用。\n"
            "原因:t2i 会生成看起来像产品、但其实不是你的产品的假图,会误导消费者。\n"
            "请改用: i2i (保留产品) / background_only (只生成背景) / composite (本地合成) / skip (只出白底图)"
        )
    if mode == SceneMode.I2I and not has_minimax_key:
        raise SceneModeError(
            "i2i 模式需要 MiniMax API key(MiniMax 是目前唯一支持 subject_reference 的供应商)。\n"
            "请在 .env 填入 MINIMAX_API_KEY,或改用其他模式。"
        )
    if mode in (SceneMode.BACKGROUND_ONLY, SceneMode.COMPOSITE) and not (
        has_minimax_key or has_dashscope_key
    ):
        raise SceneModeError(
            f"{mode.value} 模式需要至少一个图像生成 API key(DashScope 或 MiniMax)。\n"
            "请在 .env 填入对应 key,或改用 skip 模式。"
        )
