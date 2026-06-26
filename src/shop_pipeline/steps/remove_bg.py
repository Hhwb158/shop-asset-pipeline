"""Background removal step.

Uses `rembg` (ONNX model, runs locally). Outputs:
- transparent PNG (RGBA)
- white-background PNG (RGB) resized to a square canvas
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from rembg import remove

from shop_pipeline.image_utils import fit_image_on_square_canvas

# Limits
MAX_INPUT_BYTES = 10 * 1024 * 1024  # 10 MB
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}
SUPPORTED_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}


def validate_input(path: Path) -> None:
    """Validate that path exists, is a supported format, and within size limit.

    Raises:
        FileNotFoundError: path does not exist
        ValueError: format unsupported or file too large
    """
    if not path.exists():
        raise FileNotFoundError(f"Input image not found: {path}")
    if path.stat().st_size > MAX_INPUT_BYTES:
        mb = path.stat().st_size / 1024 / 1024
        raise ValueError(
            f"Input file too large: {mb:.1f} MB (max {MAX_INPUT_BYTES // 1024 // 1024} MB)"
        )
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: {path.suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )


def remove_background(src: Path, dst: Path) -> Path:
    """Remove background from src, save as RGBA PNG to dst.

    Args:
        src: input image path
        dst: output path (will be PNG, RGBA, transparent background)

    Returns:
        dst path
    """
    validate_input(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        out = remove(img)
        out.save(dst, format="PNG")
    return dst


def remove_background_to_white(
    src: Path,
    dst: Path,
    square_size: int = 1024,
) -> Path:
    """Remove background, composite onto white, resize to square canvas.

    Args:
        src: input image path
        dst: output path (PNG, RGB, white background)
        square_size: side length of output square in pixels

    Returns:
        dst path
    """
    validate_input(src)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as img:
        rgba = remove(img).convert("RGBA")

    # White background, paste RGBA on top
    canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    canvas.alpha_composite(rgba)

    final = fit_image_on_square_canvas(canvas, square_size=square_size)
    final.save(dst, format="PNG")
    return dst
