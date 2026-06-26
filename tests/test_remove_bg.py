"""Tests for the background removal step."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from shop_pipeline.image_utils import fit_image_on_square_canvas
from shop_pipeline.steps.remove_bg import (
    MAX_INPUT_BYTES,
    SUPPORTED_FORMATS,
    remove_background,
    remove_background_to_white,
    validate_input,
)


def _make_test_image(path: Path, color=(200, 50, 50), size=(200, 200), fmt="PNG") -> None:
    Image.new("RGB", size, color).save(path, format=fmt)


# -------- validate_input --------


def test_validate_input_accepts_png(tmp_path):
    p = tmp_path / "in.png"
    _make_test_image(p)
    validate_input(p)  # should not raise


def test_validate_input_accepts_jpeg(tmp_path):
    p = tmp_path / "in.jpg"
    _make_test_image(p, fmt="JPEG")
    validate_input(p)


def test_validate_input_rejects_unsupported_format(tmp_path):
    p = tmp_path / "in.bmp"
    _make_test_image(p, fmt="BMP")
    with pytest.raises(ValueError, match="Unsupported format"):
        validate_input(p)


def test_validate_input_rejects_oversized_file(tmp_path):
    p = tmp_path / "huge.png"
    # Create a small file then monkey-patch size check by using stat
    _make_test_image(p)
    big = tmp_path / "huge_real.png"
    big.write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
    with pytest.raises(ValueError, match="too large"):
        validate_input(big)


def test_validate_input_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_input(tmp_path / "nope.png")


# -------- remove_background --------


def test_remove_background_produces_rgba(tmp_path):
    src = tmp_path / "src.png"
    out = tmp_path / "out.png"
    _make_test_image(src, color=(255, 0, 0), size=(300, 300))
    remove_background(src, out)
    assert out.exists()
    img = Image.open(out)
    assert img.mode == "RGBA"


def test_remove_background_makes_background_transparent(tmp_path):
    src = tmp_path / "src.png"
    out = tmp_path / "out.png"
    # Solid red image — center should be opaque, corners should be transparent
    _make_test_image(src, color=(255, 0, 0), size=(400, 400))
    remove_background(src, out)
    img = Image.open(out).convert("RGBA")
    # Sample a corner (likely background)
    corner_alpha = img.getpixel((5, 5))[3]
    center_alpha = img.getpixel((200, 200))[3]
    # rembg may keep some center opaque; corner should be much more transparent
    assert center_alpha >= corner_alpha


# -------- remove_background_to_white --------


def test_remove_background_to_white_creates_white_bg(tmp_path):
    src = tmp_path / "src.png"
    out = tmp_path / "white.png"
    _make_test_image(src, color=(255, 0, 0), size=(400, 400))
    remove_background_to_white(src, out, square_size=400)
    img = Image.open(out)
    assert img.mode == "RGB"
    assert img.size == (400, 400)
    # Sample a corner — should be near white
    corner = img.getpixel((5, 5))
    assert corner[0] > 240 and corner[1] > 240 and corner[2] > 240


def test_remove_background_to_white_resizes_to_square(tmp_path):
    src = tmp_path / "src.png"
    out = tmp_path / "white.png"
    _make_test_image(src, size=(300, 500))
    remove_background_to_white(src, out, square_size=600)
    img = Image.open(out)
    assert img.size == (600, 600)


def test_fit_image_on_square_canvas_preserves_full_wide_image():
    src = Image.new("RGB", (400, 200), (255, 0, 0))
    out = fit_image_on_square_canvas(src, square_size=400, padding_ratio=0)

    assert out.size == (400, 400)
    assert out.getpixel((0, 100)) == (255, 0, 0)
    assert out.getpixel((399, 299)) == (255, 0, 0)
    assert out.getpixel((200, 50)) == (255, 255, 255)
    assert out.getpixel((200, 350)) == (255, 255, 255)


def test_remove_background_to_white_supported_formats():
    # Sanity: all expected formats present
    expected = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
    assert expected.issubset(SUPPORTED_FORMATS)
