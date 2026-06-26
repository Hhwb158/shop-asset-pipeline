"""Streamlit UI — shop asset generation pipeline.

Run with:
    streamlit run app.py

Key principle: NEVER silently fall back to text-to-image when the user
expects their product to appear in the scene. The mode chooser is
explicit and validated.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

# Make src importable when running `streamlit run app.py` from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from shop_pipeline.config import Config
from shop_pipeline.logging_setup import get_logger, setup_logging
from shop_pipeline.pipeline import run_pipeline
from shop_pipeline.scene_modes import MODE_DESCRIPTIONS, SceneMode, SceneModeError

st.set_page_config(
    page_title="Shop Asset Pipeline",
    page_icon="🛍️",
    layout="wide",
)

st.title("Shop Asset Pipeline")
st.caption("输入一张产品图,自动产出白底主图 / 场景图 / 产品视频")

# Config
try:
    config = Config.load(require_dashscope=False, require_kling=False)
except Exception as e:
    st.error(f"配置加载失败: {e}")
    st.stop()

with st.sidebar:
    st.header("API 状态")
    st.write("DashScope (场景图):", "OK" if config.has_dashscope() else "no key")
    st.write("Kling (视频):", "OK" if config.has_kling() else "no key")
    st.write("MiniMax (场景图 / i2i):", "OK" if config.has_minimax() else "no key")
    st.divider()
    st.header("生成设置")

    product_type = st.selectbox(
        "产品类型",
        options=["clothing", "electronics", "food", "other"],
        format_func=lambda x: {
            "clothing": "服装/鞋包",
            "electronics": "3C/小家电",
            "food": "食品/日用",
            "other": "其他",
        }[x],
    )

    square_size = st.selectbox(
        "主图尺寸",
        options=[800, 1024, 1200, 2000],
        index=1,
        help="淘宝/天猫合规要求 800x800 以上",
    )

    # === Scene mode selector (THE CRITICAL CHOICE) ===
    st.subheader("场景图模式")
    st.caption(
        "不同模式决定:场景图里**是否真有你的产品**。\n"
        "**不会**用文生图冒充产品照(那种是假图)。"
    )

    # Build available mode list with availability check
    available_modes: list[SceneMode] = []
    if config.has_minimax():
        available_modes.append(SceneMode.I2I)
    if config.has_dashscope() or config.has_minimax():
        available_modes.append(SceneMode.BACKGROUND_ONLY)
    available_modes.append(SceneMode.SKIP)  # always available

    if "scene_mode" not in st.session_state:
        # Default to I2I if available, else BACKGROUND_ONLY, else SKIP
        st.session_state["scene_mode"] = (
            SceneMode.I2I
            if SceneMode.I2I in available_modes
            else (SceneMode.BACKGROUND_ONLY if available_modes else SceneMode.SKIP)
        )

    # Use radio with mode descriptions
    mode_options = available_modes
    selected_mode = st.radio(
        "选择场景图模式",
        options=mode_options,
        format_func=lambda m: f"{m.value} — {MODE_DESCRIPTIONS[m]}",
        key="scene_mode",
    )

    if selected_mode == SceneMode.I2I:
        st.info(
            "i2i 模式:会用你的产品图作为参考,生成的场景图**保留产品外形**。\n"
            "需要把白底图上传到 litterbox.catbox.moe(默认,匿名免费,1h 过期)。"
        )
    elif selected_mode == SceneMode.BACKGROUND_ONLY:
        st.warning(
            "仅背景模式:生成的图**不含产品**,适合你后期自己用 Photoshop 合成。"
        )
    elif selected_mode == SceneMode.SKIP:
        st.info("跳过场景图,只输出白底主图。")

    do_video = st.checkbox(
        "生成产品视频", value=config.has_kling(), disabled=not config.has_kling()
    )
    subtitle = st.text_input("视频字幕(可选,中文)", value="新品上市,限时特惠")

# Main: upload
st.header("1. 上传产品图")
uploaded = st.file_uploader(
    "支持 PNG / JPG / WEBP / HEIC,最大 10MB",
    type=["png", "jpg", "jpeg", "webp", "heic", "heif"],
    accept_multiple_files=False,
)

if uploaded is not None:
    from shop_pipeline.steps.remove_bg import MAX_INPUT_BYTES

    if uploaded.size > MAX_INPUT_BYTES:
        st.error(f"文件太大: {uploaded.size / 1024 / 1024:.1f} MB (最大 10MB)")
        st.stop()

    product_id = uuid.uuid4().hex[:8]
    work_dir = Path("outputs") / product_id
    work_dir.mkdir(parents=True, exist_ok=True)
    ext = uploaded.name[uploaded.name.rfind(".") :]
    src_path = work_dir / f"source{ext}"
    src_path.write_bytes(uploaded.getbuffer())
    st.success(f"已保存到 {src_path} (产品 ID: {product_id})")

    col1, col2 = st.columns(2)
    with col1:
        st.image(src_path, caption="原始产品图", use_container_width=True)

    product_desc = st.text_input(
        "产品描述(用于场景图 prompt)",
        value=uploaded.name.rsplit(".", 1)[0],
        help="用中文或英文简述产品,如 '红色棉质 T 恤'",
    )

    st.header("2. 一键生成")
    st.caption(f"将使用场景图模式: **{selected_mode.value}**")
    if st.button("开始生成", type="primary"):
        setup_logging(log_file=work_dir / "log.txt")
        log = get_logger("shop_pipeline.ui")
        log.info("UI start: id=%s mode=%s", product_id, selected_mode.value)

        with st.status("正在生成...", expanded=True) as status:
            status_text = st.empty()

            def on_progress(stage: str, detail: str = "") -> None:
                msg = f"**[{stage}]** {detail}"
                status_text.markdown(msg)
                log.info("[%s] %s", stage, detail)

            try:
                result = run_pipeline(
                    config=config,
                    product_image_path=src_path,
                    product_type=product_type,
                    product_desc=product_desc,
                    work_dir=work_dir,
                    square_size=square_size,
                    generate_video=do_video,
                    subtitle_text=subtitle if subtitle else None,
                    scene_mode=selected_mode,
                    on_progress=on_progress,
                )
                status.update(label="生成完成", state="complete")
            except SceneModeError as e:
                log.exception("scene mode validation failed")
                status.update(label="场景图模式被拒", state="error")
                st.error(f"**场景图生成被拒绝**\n\n{e}")
                st.stop()
            except Exception as e:
                log.exception("pipeline failed")
                st.error(f"生成失败: {e}")
                st.stop()

        # Display results
        st.header("3. 结果")
        st.subheader("白底主图")
        st.image(str(result.white_bg_path), width=400)
        with open(result.white_bg_path, "rb") as f:
            st.download_button(
                "下载白底主图",
                f,
                file_name=result.white_bg_path.name,
                mime="image/png",
            )

        if result.scenes:
            st.subheader(f"场景图 ({len(result.scenes)} 张 · 模式={result.scene_mode.value})")
            cols = st.columns(min(len(result.scenes), 4))
            for i, s in enumerate(result.scenes):
                with cols[i % 4]:
                    st.image(str(s.image_path), caption=s.name, use_container_width=True)
                    with open(s.image_path, "rb") as f:
                        st.download_button(
                            f"下载 {s.name}",
                            f,
                            file_name=s.image_path.name,
                            mime="image/png",
                            key=f"dl-scene-{s.name}",
                        )
        else:
            st.caption(f"未生成场景图(模式: {result.scene_mode.value})")

        if result.video:
            st.subheader("产品视频")
            st.video(str(result.video.video_path))
            with open(result.video.video_path, "rb") as f:
                st.download_button(
                    "下载视频",
                    f,
                    file_name=result.video.video_path.name,
                    mime="video/mp4",
                )
        elif do_video:
            st.info("视频未生成(需配置 KLING_API_KEY 或未实现公开图床上传)")

        st.success(f"全部素材已保存到 `{work_dir}`")

else:
    st.info("请先上传产品图")
    st.markdown(
        """
        ### 建议
        - 拍摄时**光线均匀**,产品居中
        - 背景尽量简洁(纯色/简单桌面都行)
        - 像素 >= 800x800,效果更好

        ### 5 分钟上手
        1. `pip install -r requirements.txt`
        2. 复制 `.env.example` 为 `.env`,填入 API key
        3. `streamlit run app.py`
        """
    )
