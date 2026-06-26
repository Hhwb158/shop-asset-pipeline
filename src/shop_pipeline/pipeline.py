"""Top-level pipeline orchestration.

Combines all steps: remove_bg → generate_scenes → generate_video.
Each step writes to its own subdirectory under the work dir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shop_pipeline.config import Config
from shop_pipeline.logging_setup import get_logger
from shop_pipeline.steps.generate_scene import SceneOutput, generate_scenes
from shop_pipeline.steps.generate_video import VideoOutput, generate_product_video
from shop_pipeline.steps.remove_bg import remove_background_to_white

log = get_logger("shop_pipeline.pipeline")


@dataclass(frozen=True)
class PipelineResult:
    """Aggregate output of running the full pipeline."""

    product_id: str
    work_dir: Path
    white_bg_path: Path
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
    """Override this in production to upload to your CDN / OSS / S3.

    For now we just point to a placeholder so the pipeline still works
    end-to-end (Kling will fail on the placeholder URL, which is
    expected — user must wire up real upload).
    """
    raise NotImplementedError(PUBLIC_IMAGE_HOST_NOTE)


def run_pipeline(
    config: Config,
    product_image_path: Path,
    product_type: str,
    product_desc: str,
    work_dir: Path,
    square_size: int = 1024,
    generate_video: bool = True,
    subtitle_text: str | None = None,
    on_progress: Callable[[str, str], None] | None = None,
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
        on_progress: callback(stage, detail) for UI updates

    Returns:
        PipelineResult with all generated asset paths
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    product_id = work_dir.name
    log.info("pipeline start: id=%s type=%s", product_id, product_type)

    # Step 1: white-bg main image
    def progress(stage: str, detail: str = "") -> None:
        if on_progress:
            on_progress(stage, detail)
        log.info("[%s] %s", stage, detail)

    progress("white-bg", "starting")
    white_path = work_dir / f"main-white-{square_size}.png"
    remove_background_to_white(product_image_path, white_path, square_size=square_size)
    progress("white-bg", str(white_path.name))

    # Step 2: scene images (requires DashScope)
    scenes: list[SceneOutput] = []
    if not config.has_dashscope():
        log.warning("DASHSCOPE_API_KEY not set — skipping scene generation")
    else:
        progress("scenes", "starting")
        scenes = generate_scenes(
            api_key=config.dashscope_api_key or "",
            product_image_path=white_path,
            product_type=product_type,
            product_desc=product_desc,
            out_dir=work_dir / "scenes",
            on_progress=lambda name: progress("scenes", name),
        )
        progress("scenes", f"done: {len(scenes)} images")

    # Step 3: product video (requires Kling + public image URL)
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
                    prompt=f"Smooth cinematic motion of {product_desc}, "
                    "gentle rotation, soft lighting, product showcase",
                    out_path=video_path,
                    duration=5,
                    subtitle_text=subtitle_text,
                    on_progress=lambda stage: progress("video", stage),
                )
                progress("video", str(video_path.name))

    progress("done", "all stages complete")
    return PipelineResult(
        product_id=product_id,
        work_dir=work_dir,
        white_bg_path=white_path,
        scenes=scenes,
        video=video_result,
    )
