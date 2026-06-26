"""Top-level pipeline orchestration.

Combines all steps: remove_bg → generate_scenes → generate_video.
Each step writes to its own subdirectory under the work dir.

Supports pluggable image provider (DashScope or MiniMax) and
optional subject-reference (image-to-image) mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from shop_pipeline.clients import (
    ImageProvider,
    get_image_client,
    list_available_providers,
    provider_available,
)
from shop_pipeline.config import Config
from shop_pipeline.logging_setup import get_logger
from shop_pipeline.steps.generate_scene import SceneOutput, generate_scenes_v2
from shop_pipeline.steps.generate_video import VideoOutput, generate_product_video
from shop_pipeline.steps.remove_bg import remove_background_to_white

log = get_logger("shop_pipeline.pipeline")


@dataclass(frozen=True)
class PipelineResult:
    """Aggregate output of running the full pipeline."""

    product_id: str
    work_dir: Path
    white_bg_path: Path
    image_provider: ImageProvider | None
    scenes: list[SceneOutput] = field(default_factory=list)
    video: VideoOutput | None = None


# Public CDN-like upload (for Kling's image_url field).
# In production you'd upload to OSS / S3 / etc. For now we skip video
# generation when no public host is available; caller can wire one in.
PUBLIC_IMAGE_HOST_NOTE = (
    "Video generation needs a publicly accessible image URL. "
    "Either upload the white-bg image to a CDN and pass that URL, "
    "or implement upload_to_public_host() in pipeline.py."
)


def upload_to_public_host(local_path: Path) -> str:
    """Override this in production to upload to your CDN / OSS / S3."""
    raise NotImplementedError(PUBLIC_IMAGE_HOST_NOTE)


def _resolve_provider(
    config: Config,
    image_provider: ImageProvider | str | None,
) -> ImageProvider | None:
    """Pick the image provider, validating the API key is available.

    Priority:
      1. Explicit `image_provider` argument
      2. First available in [DashScope, MiniMax] (deterministic order)
      3. None (caller will skip scene generation)
    """
    if image_provider is not None:
        if isinstance(image_provider, str):
            image_provider = ImageProvider(image_provider)
        if not provider_available(image_provider, config):
            available = list_available_providers(config)
            raise ValueError(
                f"Provider {image_provider.value} not configured. "
                f"Available: {[p.value for p in available] or 'none'}"
            )
        return image_provider
    available = list_available_providers(config)
    return available[0] if available else None


def _api_key_for(config: Config, provider: ImageProvider) -> str:
    if provider == ImageProvider.DASHSCOPE:
        return config.dashscope_api_key or ""
    if provider == ImageProvider.MINIMAX:
        return config.minimax_api_key or ""
    raise ValueError(f"No API key mapping for provider: {provider}")


def run_pipeline(
    config: Config,
    product_image_path: Path,
    product_type: str,
    product_desc: str,
    work_dir: Path,
    square_size: int = 1024,
    generate_video: bool = True,
    subtitle_text: str | None = None,
    image_provider: ImageProvider | str | None = None,
    use_subject_reference: bool = False,
    on_progress: Callable[[str, str], None] | None = None,
    http_client: httpx.Client | None = None,
) -> PipelineResult:
    """Run the full asset generation pipeline.

    Args:
        config: loaded Config
        product_image_path: local product image
        product_type: clothing | electronics | food | other
        product_desc: short description for prompt generation
        work_dir: where to save outputs
        square_size: white-bg output side length
        generate_video: whether to also generate product video
        subtitle_text: optional Chinese subtitle for the video
        image_provider: 'dashscope' | 'minimax' | None (auto-pick first available)
        use_subject_reference: when True and provider is MiniMax, use i2i endpoint
        on_progress: callback(stage, detail) for UI updates
        http_client: optional httpx.Client (for tests with MockTransport)
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    product_id = work_dir.name
    log.info(
        "pipeline start: id=%s type=%s provider=%s i2i=%s",
        product_id, product_type, image_provider, use_subject_reference,
    )

    own_client = http_client is None
    http = http_client or httpx.Client(timeout=120.0)

    def progress(stage: str, detail: str = "") -> None:
        if on_progress:
            on_progress(stage, detail)
        log.info("[%s] %s", stage, detail)

    try:
        # Step 1: white-bg main image (always local, no API)
        progress("white-bg", "starting")
        white_path = work_dir / f"main-white-{square_size}.png"
        remove_background_to_white(product_image_path, white_path, square_size=square_size)
        progress("white-bg", str(white_path.name))

        # Step 2: scene images
        scenes: list[SceneOutput] = []
        selected_provider: ImageProvider | None = None
        try:
            selected_provider = _resolve_provider(config, image_provider)
        except ValueError as e:
            log.warning("provider resolution failed: %s", e)
            progress("scenes", f"skipped: {e}")

        if selected_provider is None:
            log.warning(
                "no image provider available — skipping scene generation "
                "(set DASHSCOPE_API_KEY or MINIMAX_API_KEY)"
            )
            progress("scenes", "skipped: no image provider configured")
        else:
            progress("scenes", f"using {selected_provider.value}")
            image_client = get_image_client(
                selected_provider, use_subject_reference=use_subject_reference
            )
            scenes = generate_scenes_v2(
                image_client=image_client,
                api_key=_api_key_for(config, selected_provider),
                product_image_path=white_path,
                product_type=product_type,
                product_desc=product_desc,
                out_dir=work_dir / "scenes",
                on_progress=lambda name: progress("scenes", name),
                client=http,
            )
            progress("scenes", f"done: {len(scenes)} images")

        # Step 3: product video
        video_result: VideoOutput | None = None
        if generate_video:
            if not config.has_kling():
                log.warning("KLING_API_KEY not set — skipping video generation")
            else:
                progress("video", "uploading image")
                try:
                    image_url = upload_to_public_host(white_path)
                except NotImplementedError as e:
                    log.warning("video skipped: %s", e)
                else:
                    progress("video", "generating")
                    video_path = work_dir / "video" / "product-intro.mp4"
                    video_path.parent.mkdir(parents=True, exist_ok=True)
                    video_result = generate_product_video(
                        api_key=config.kling_api_key or "",
                        api_secret=config.kling_api_secret or "",
                        image_url=image_url,
                        prompt=(
                            f"Smooth cinematic motion of {product_desc}, "
                            "gentle rotation, soft lighting, product showcase"
                        ),
                        out_path=video_path,
                        duration=5,
                        subtitle_text=subtitle_text,
                        on_progress=lambda stage: progress("video", stage),
                        client=http,
                    )
                    progress("video", str(video_path.name))

        progress("done", "all stages complete")
        return PipelineResult(
            product_id=product_id,
            work_dir=work_dir,
            white_bg_path=white_path,
            image_provider=selected_provider,
            scenes=scenes,
            video=video_result,
        )
    finally:
        if own_client:
            http.close()

