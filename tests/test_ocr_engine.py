"""Unit tests for the OCR document-ingestion service (fake engine, no OCR libs)."""

from __future__ import annotations

import io

import numpy as np
import pymupdf
import pytest
from PIL import Image

from ocr_engine.base import OCREngine
from ocr_engine.raster import page_to_array
from ocr_engine.service import PageText, extract_text_from_bytes


class FakeEngine(OCREngine):
    """OCR engine that returns canned text per call and records images."""

    def __init__(self, texts: list[str | Exception]) -> None:
        self._queue = list(texts)
        self.calls: list[np.ndarray] = []

    @property
    def name(self) -> str:
        return "fake"

    def recognize(self, image: np.ndarray) -> str:
        self.calls.append(image)
        if not self._queue:
            return ""
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.calls.clear()


def _pdf_bytes(*page_texts: str | None) -> bytes:
    """Build an in-memory PDF; ``None`` yields a blank (scanned-like) page."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), color=(255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_pdf_text_layer_is_used_without_ocr() -> None:
    engine = FakeEngine([])
    result = extract_text_from_bytes(_pdf_bytes("Jane owes $1000."), "claim.pdf", engine=engine)
    assert engine.calls == []
    assert result.warnings == []
    assert result.pages == [PageText(1, "Jane owes $1000.", "text")]
    assert result.full_text == "Jane owes $1000."


def test_blank_pdf_page_falls_back_to_ocr() -> None:
    engine = FakeEngine(["OCR TEXT"])
    result = extract_text_from_bytes(
        _pdf_bytes("Embedded page", None), "claim.pdf", engine=engine
    )
    assert len(engine.calls) == 1
    assert [(p.page, p.source) for p in result.pages] == [(1, "text"), (2, "ocr")]
    assert result.pages[1].text == "OCR TEXT"
    assert "Embedded page" in result.full_text
    assert "OCR TEXT" in result.full_text


def test_raster_image_goes_through_ocr() -> None:
    engine = FakeEngine(["IMAGE TEXT"])
    result = extract_text_from_bytes(_png_bytes(), "scan.png", engine=engine)
    assert len(engine.calls) == 1
    assert engine.calls[0].ndim == 3
    assert result.pages == [PageText(1, "IMAGE TEXT", "ocr")]
    assert result.full_text == "IMAGE TEXT"


def test_multiple_ocr_pages_preserve_order() -> None:
    engine = FakeEngine(["first page text", "second page text"])
    result = extract_text_from_bytes(_pdf_bytes(None, None), "scan.pdf", engine=engine)
    assert [(p.page, p.text) for p in result.pages] == [
        (1, "first page text"),
        (2, "second page text"),
    ]
    assert result.full_text == "first page text\n\nsecond page text"


def test_per_page_ocr_failure_becomes_warning() -> None:
    engine = FakeEngine(["ok text", RuntimeError("boom")])
    result = extract_text_from_bytes(_pdf_bytes(None, None), "scan.pdf", engine=engine)
    assert result.pages[0].text == "ok text"
    assert result.pages[1].text == ""
    assert len(result.warnings) == 1
    assert "page 2" in result.warnings[0]
    assert "boom" in result.warnings[0]


def test_uses_default_engine_when_none_supplied(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEngine(["default text"])
    monkeypatch.setattr("ocr_engine.service._get_default_engine", lambda: fake)
    result = extract_text_from_bytes(_png_bytes(), "scan.png")
    assert result.pages == [PageText(1, "default text", "ocr")]


def test_empty_file_yields_warning() -> None:
    result = extract_text_from_bytes(b"", "empty.pdf", engine=FakeEngine([]))
    assert result.pages == []
    assert result.full_text == ""
    assert result.warnings == ["empty file"]


def test_unreadable_content_yields_warning() -> None:
    engine = FakeEngine([])
    result = extract_text_from_bytes(b"definitely not an image", "junk.txt", engine=engine)
    assert result.pages == []
    assert engine.calls == []
    assert len(result.warnings) == 1


def test_malformed_pdf_yields_warning() -> None:
    result = extract_text_from_bytes(b"%PDF-not-a-real-file", "bad.pdf", engine=FakeEngine([]))
    assert result.pages == []
    assert len(result.warnings) == 1


def test_page_to_array_returns_rgb_image() -> None:
    doc = pymupdf.open()
    doc.new_page()
    page = doc[0]
    try:
        array = page_to_array(page, dpi=72)
    finally:
        doc.close()
    assert array.ndim == 3
    assert array.shape[2] == 3
    assert array.dtype == np.uint8
