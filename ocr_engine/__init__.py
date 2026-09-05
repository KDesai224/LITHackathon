"""OCR document ingestion for ClaimReady.

Public surface:

- Engines: :class:`OCREngine`, :class:`RapidEngine`, ``OCRUnavailableError``,
  ``rapidocr_available``, ``default_engine``
- Ingestion: ``extract_text_from_bytes``, ``DocumentResult``, ``PageText``
"""

from __future__ import annotations

import threading

from ocr_engine.base import OCREngine
from ocr_engine.rapid_engine import (
    OCRUnavailableError,
    RapidEngine,
    rapidocr_available,
)
from ocr_engine.service import (
    DocumentResult,
    PageText,
    extract_text_from_bytes,
)

__all__ = [
    "DocumentResult",
    "OCREngine",
    "OCRUnavailableError",
    "PageText",
    "RapidEngine",
    "default_engine",
    "extract_text_from_bytes",
    "rapidocr_available",
]

_ENGINE: OCREngine | None = None
_ENGINE_LOCK = threading.Lock()


def default_engine() -> OCREngine:
    """Return the process-wide OCR engine, constructing it lazily once."""
    global _ENGINE
    engine = _ENGINE
    if engine is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = RapidEngine()
            engine = _ENGINE
    return engine
