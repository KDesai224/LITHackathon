"""Slow integration test: real rapidocr engine on a rendered-text image.

Marked ``slow`` so the default local run skips it; CI runs it on push via the
``uv run pytest -m slow`` step. No downloads or system dependencies: the ONNX
models ship inside the ``rapidocr`` wheel.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from ocr_engine import RapidEngine, rapidocr_available

pytestmark = pytest.mark.slow

_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
)


def _find_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _text_image(text: str = "CLAIM 1500") -> np.ndarray:
    font = _find_font(120)
    image = Image.new("RGB", (1500, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((40, 60), text, fill=(0, 0, 0), font=font)
    return np.asarray(image)


def test_rapid_engine_recognises_rendered_text() -> None:
    if not rapidocr_available():
        pytest.skip("rapidocr is not installed")
    engine = RapidEngine()
    try:
        text = engine.recognize(_text_image())
    finally:
        engine.close()

    normalized = re.sub(r"\s+", "", text).upper()
    assert any(token in normalized for token in ("CLAIM", "1500")), (
        f"OCR output did not contain expected tokens: {text!r}"
    )
