"""Top-level pipeline orchestration.

Combines all steps: remove_bg → generate_scenes (per SceneMode) → generate_video.
Each step writes to its own subdirectory under the work dir.

Scene mode is now strictly controlled via SceneMode (see scene_modes.py).
We MUST NOT silently fall back to text-to-image when i2i is requested but
not configured — that produces fake product images. Instead, the pipeline
validates the mode and raises SceneModeError with a clear message.
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
)
from shop_pipeline.config import Config
from shop_pipeline.logging_setup import get_logger
from shop_pipeline.public_upload import upload_to_public_host
from shop_pipeline.scene_modes import SceneMode, SceneModeError, validate_scene_mode
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
    scene_mode: SceneMode
    image_provider: ImageProvider | None
    scenes: list[SceneOutput] = field(default_factory=list)
    video: VideoOutput | None = None


def _provider_for_mode(config: Config, mode: SceneMode) -> ImageProvider | None:
    """Pick the provider to use for the given scene mode.

    I2I requires MiniMax; others use the first available.
    Returns None if no provider matches.
    """
    if mode == SceneMode.I2I:
        return ImageProvider.MINIMAX if config.has_minimax() else None
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
    scene_mode: SceneMode | str = SceneMode.SKIP,
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
        scene_mode: SceneMode.SKIP (only white-bg) / I2I (real product) /
            BACKGROUND_ONLY (no product in scene) / COMPOSITE (local PIL merge)
        on_progress: callback(stage, detail) for UI updates
        http_client: optional httpx.Client (for tests with MockTransport)

    Raises:
        SceneModeError: when the requested mode cannot be applied right now
            (e.g. I2I without MiniMax key, or T2I which is disabled)
    """
    if isinstance(scene_mode, str):
        scene_mode = SceneMode(scene_mode)

    # Step 0: validate scene mode up front — fail fast with clear message
    validate_scene_mode(
        scene_mode,
        has_minimax_key=config.has_minimax(),
        has_dashscope_key=config.has_dashscope(),
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    product_id = work_dir.name
    log.info(
        "pipeline start: id=%s type=%s scene_mode=%s",
        product_id, product_type, scene_mode.value,
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

        # Step 2: scene images (mode-driven)
        scenes: list[SceneOutput] = []
        selected_provider: ImageProvider | None = None
        if scene_mode == SceneMode.SKIP:
            progress("scenes", "skipped (mode=skip)")
        else:
            selected_provider = _provider_for_mode(config, scene_mode)
            if selected_provider is None:
                # Should be unreachable: validate_scene_mode raised for these cases
                raise SceneModeError(
                    f"scene_mode={scene_mode.value} requires a provider, but none available"
                )
            progress("scenes", f"using {selected_provider.value} (mode={scene_mode.value})")
            image_client = get_image_client(selected_provider, use_subject_reference=False)

            subject_url: str | None = None
            if scene_mode == SceneMode.I2I:
                # Pre-upload the white-bg to a public host so MiniMax i2i can use it
                progress("scenes", "uploading white-bg to public host")
                subject_url = upload_to_public_host(white_path)
                (work_dir / "scenes").mkdir(parents=True, exist_ok=True)
                (work_dir / "scenes" / "litterbox_url.txt").write_text(
                    f"product_image_url={subject_url}\n",
                    encoding="utf-8",
                )
                log.info("uploaded to: %s", subject_url)

            scenes = generate_scenes_v2(
                image_client=image_client,
                api_key=_api_key_for(config, selected_provider),
                product_image_path=white_path,
                product_type=product_type,
                product_desc=product_desc,
                out_dir=work_dir / "scenes",
                on_progress=lambda name: progress("scenes", name),
                client=http,
                subject_image_url=subject_url,
                mode=scene_mode,
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
            scene_mode=scene_mode,
            image_provider=selected_provider,
            scenes=scenes,
            video=video_result,
        )
    finally:
        if own_client:
            http.close()
