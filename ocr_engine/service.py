"""Document ingestion: extract readable text from PDFs and raster images.

Born-digital PDFs contribute their embedded text layer per page; pages with no
selectable text (and all raster images) are passed through an OCR engine. A
single engine instance is reused across pages, and the consumer receives one
:class:`DocumentResult` with page order preserved.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Literal, cast

import numpy as np
import pymupdf
from PIL import Image, ImageSequence, UnidentifiedImageError

from ocr_engine.base import OCREngine
from ocr_engine.rapid_engine import OCRUnavailableError
from ocr_engine.raster import page_to_array

PageSource = Literal["text", "ocr"]


@dataclass
class PageText:
    """Text extracted from a single page of a document."""

    page: int  # 1-based page number
    text: str
    source: PageSource  # "text" = embedded text layer, "ocr" = recognised image


@dataclass
class DocumentResult:
    """Readable text for one uploaded file."""

    filename: str
    pages: list[PageText]
    full_text: str
    warnings: list[str] = field(default_factory=list)


def _get_default_engine() -> OCREngine:
    """Resolve the process-wide engine (lazy; patchable in tests)."""
    from ocr_engine import default_engine

    return default_engine()


def _recognize_page(
    image: np.ndarray,
    engine: OCREngine,
    page_number: int,
    warnings: list[str],
) -> str:
    """Run OCR on one page, converting failures into warnings."""
    try:
        return engine.recognize(image).strip()
    except OCRUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - per-page OCR failures are warnings
        warnings.append(f"page {page_number}: OCR failed ({engine.name}): {exc}")
        return ""


def _process_pdf(
    content: bytes,
    engine: OCREngine | None,
    warnings: list[str],
) -> list[PageText]:
    pages: list[PageText] = []
    ocr_engine = engine
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - malformed PDFs become warnings
        warnings.append(f"could not open PDF: {exc}")
        return pages
    try:
        for index in range(doc.page_count):
            page = doc[index]
            page_number = index + 1
            embedded = cast(str, page.get_text("text")).strip()
            if embedded:
                pages.append(PageText(page_number, embedded, "text"))
                continue

            if ocr_engine is None:
                ocr_engine = _get_default_engine()
            image = page_to_array(page)
            text = _recognize_page(image, ocr_engine, page_number, warnings)
            pages.append(PageText(page_number, text, "ocr"))
    finally:
        doc.close()
    return pages


def _process_image(
    content: bytes,
    engine: OCREngine | None,
    warnings: list[str],
) -> list[PageText]:
    pages: list[PageText] = []
    try:
        image = Image.open(io.BytesIO(content))
        frames = list(ImageSequence.Iterator(image))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        warnings.append(f"could not read image: {exc}")
        return pages

    ocr_engine = engine
    if ocr_engine is None:
        ocr_engine = _get_default_engine()
    for index, frame in enumerate(frames):
        page_number = index + 1
        array = np.asarray(frame.convert("RGB"))
        text = _recognize_page(array, ocr_engine, page_number, warnings)
        pages.append(PageText(page_number, text, "ocr"))
    return pages


def extract_text_from_bytes(
    content: bytes,
    filename: str,
    *,
    engine: OCREngine | None = None,
) -> DocumentResult:
    """Extract readable text from an uploaded PDF or raster image.

    Args:
        content: Raw file bytes.
        filename: Original filename (used only for reporting).
        engine: Optional OCR engine. When omitted, the process-wide
            :func:`ocr_engine.default_engine` is used for any page that needs
            OCR. An unavailable engine raises :class:`OCRUnavailableError`.

    Returns:
        A :class:`DocumentResult` with per-page text, page order preserved.
    """
    warnings: list[str] = []
    if not content:
        return DocumentResult(filename, [], "", ["empty file"])

    is_pdf = content[:5].startswith(b"%PDF")
    pages = (
        _process_pdf(content, engine, warnings)
        if is_pdf
        else _process_image(content, engine, warnings)
    )

    full_text = "\n\n".join(page.text for page in pages if page.text.strip())
    return DocumentResult(filename, pages, full_text, warnings)
