"""RapidOCR (onnxruntime) engine implementation.

Wraps the ``rapidocr`` package. The ONNX models are bundled inside the
``rapidocr`` wheel, so no runtime downloads or system dependencies are needed.
The engine and its inference session are created lazily and reused for every
page (single instance per process via :func:`ocr_engine.default_engine`).
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from ocr_engine.base import OCREngine


class OCRUnavailableError(RuntimeError):
    """Raised when the rapidocr backend cannot be imported or initialised."""


def rapidocr_available() -> bool:
    """Return True if the ``rapidocr`` package can be imported."""
    try:
        from rapidocr import RapidOCR  # noqa: F401
    except Exception:  # noqa: BLE001 - any import error means unavailable
        return False
    return True


def _line_sort_key(item: tuple[str, Any]) -> tuple[float, float]:
    """Sort key that orders OCR lines top-to-bottom, then left-to-right.

    ``rapidocr`` boxes are ``(x1, y1, x2, y2)``; a missing or malformed box
    sorts first (top of page).
    """
    _, box = item
    if box is None:
        return (0.0, 0.0)
    try:
        flat = np.asarray(box).ravel().astype(float)
        if flat.size < 4:
            return (0.0, 0.0)
        return (float(flat[1]), float(flat[0]))
    except (TypeError, ValueError):
        return (0.0, 0.0)


class RapidEngine(OCREngine):
    """OCR engine backed by rapidocr's onnxruntime pipeline."""

    def __init__(self) -> None:
        self._engine: Any | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "rapidocr"

    def _get_engine(self) -> Any:
        engine = self._engine
        if engine is not None:
            return engine
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr import RapidOCR
                except ImportError as exc:
                    raise OCRUnavailableError(
                        "rapidocr is not installed"
                    ) from exc
                try:
                    self._engine = RapidOCR()
                except Exception as exc:  # surface init failure to caller
                    raise OCRUnavailableError(
                        f"Failed to initialise rapidocr: {exc}"
                    ) from exc
            engine = self._engine
        return engine

    def recognize(self, image: np.ndarray) -> str:
        engine = self._get_engine()
        try:
            result = engine(image)
        except Exception as exc:  # surface provider failure to caller
            raise OCRUnavailableError(f"rapidocr inference failed: {exc}") from exc

        txts = getattr(result, "txts", None)
        if not txts:
            return ""
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            boxes = [None] * len(txts)

        lines = sorted(zip(txts, boxes), key=_line_sort_key)
        return "\n".join(text.strip() for text, _ in lines if text and text.strip())

    def close(self) -> None:
        engine = self._engine
        self._engine = None
        del engine
