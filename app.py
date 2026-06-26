"""Streamlit UI — shop asset generation pipeline.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

# Make src importable when running `streamlit run app.py` from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from shop_pipeline.clients import (
    ImageProvider,
    list_available_providers,
)
from shop_pipeline.config import Config
from shop_pipeline.logging_setup import get_logger, setup_logging
from shop_pipeline.pipeline import run_pipeline

st.set_page_config(
    page_title="Shop Asset Pipeline",
    page_icon="🛍️",
    layout="wide",
)

st.title("🛍️ 店铺素材流水线")
st.caption("输入一张产品图,自动产出白底主图 / 场景图 / 产品视频")

# Config
try:
    config = Config.load(require_dashscope=False, require_kling=False)
except Exception as e:
    st.error(f"配置加载失败: {e}")
    st.stop()

PROVIDER_LABELS = {
    ImageProvider.DASHSCOPE: "DashScope (通义千问 / 阿里)",
    ImageProvider.MINIMAX: "MiniMax (Xiyu / image-01)",
}

with st.sidebar:
    st.header("API 状态")
    st.write("DashScope (场景图):", "✅" if config.has_dashscope() else "❌ 未配置")
    st.write("Kling (视频):", "✅" if config.has_kling() else "❌ 未配置")
    st.write("MiniMax (场景图):", "✅" if config.has_minimax() else "❌ 未配置")
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

    # Image provider selection (only show available ones)
    available = list_available_providers(config)
    if not available:
        st.error("未配置任何图像 API key,无法生成场景图")
        selected_provider: ImageProvider | None = None
        do_scenes = False
    else:
        labels = [PROVIDER_LABELS[p] for p in available]
        idx = st.selectbox(
            "图像生成 Provider",
            options=range(len(available)),
            format_func=lambda i: labels[i],
            help="选择用哪家的 API 生成场景图",
        )
        selected_provider = available[idx]
        do_scenes = st.checkbox("生成场景图", value=True)

        # Subject reference only makes sense for MiniMax (i2i mode)
        if selected_provider == ImageProvider.MINIMAX:
            use_subject_reference = st.checkbox(
                "图生图(保留产品特征)",
                value=False,
                help="勾选后用产品图作为参考生成场景(MiniMax i2i 模式);"
                "未勾选用纯文生图。需要产品图有公网 URL。",
            )
        else:
            use_subject_reference = False
            st.caption("(DashScope 总是用参考图,无需选择)")

    square_size = st.selectbox(
        "主图尺寸",
        options=[800, 1024, 1200, 2000],
        index=1,
        help="淘宝/天猫合规要求 800x800 以上",
    )

    do_video = st.checkbox(
        "生成产品视频", value=config.has_kling(), disabled=not config.has_kling()
    )
    subtitle = st.text_input("视频字幕(可选,中文)", value="新品上市,限时特惠")

# Main: upload
st.header("① 上传产品图")
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

    st.header("② 一键生成")
    if st.button("🚀 开始生成", type="primary"):
        setup_logging(log_file=work_dir / "log.txt")
        log = get_logger("shop_pipeline.ui")
        log.info("UI start: id=%s provider=%s", product_id, selected_provider)

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
                    image_provider=selected_provider if do_scenes else None,
                    use_subject_reference=(
                        use_subject_reference
                        if selected_provider == ImageProvider.MINIMAX
                        else False
                    ),
                    on_progress=on_progress,
                )
                status.update(label="✓ 生成完成", state="complete")
            except Exception as e:
                log.exception("pipeline failed")
                st.error(f"生成失败: {e}")
                st.stop()

        # Display results
        st.header("③ 结果")
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
            provider_label = (
                PROVIDER_LABELS.get(result.image_provider, "?") if result.image_provider else "?"
            )
            st.subheader(f"场景图({len(result.scenes)} 张 · {provider_label})")
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
    st.info("👆 请先上传产品图")
    st.markdown(
        """
        ### 建议
        - 拍摄时**光线均匀**,产品居中
        - 背景尽量简洁(纯色/简单桌面都行)
        - 像素 ≥ 800x800,效果更好

        ### 5 分钟上手
        1. `pip install -r requirements.txt`
        2. 复制 `.env.example` 为 `.env`,填入 API key
        3. `streamlit run app.py`
        """
    )
