"""Tests for ``run_document_intake``: OCR gating + typed text + fast path.

OCR engine is a local recording double, so no OCR libraries or network are
touched; field extraction uses a canned mapping extractor.
"""

from __future__ import annotations

import io
from typing import Any

import pymupdf
import pytest
from PIL import Image

from sct_intake import DocumentIntakeResult, IngestedFile, run_document_intake


class RecordingEngine:
    """Minimal OCREngine double that records every raster it is given."""

    def __init__(self, texts: list[str]) -> None:
        self._queue = list(texts)
        self.calls: list[Any] = []

    @property
    def name(self) -> str:
        return "recording"

    def recognize(self, image: Any) -> str:
        self.calls.append(image)
        return self._queue.pop(0) if self._queue else ""

    def close(self) -> None:
        self.calls.clear()


def _pdf_bytes(*page_texts: str | None) -> bytes:
    """In-memory PDF; ``None`` yields a blank (scanned-like) page."""
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


def _capturing_extractor(seen: list[str]) -> Any:
    def extract(text: str) -> dict[str, str]:
        seen.append(text)
        return {"claimant_name": "Jane", "respondent_name": "Ong"}

    return extract


def test_text_layer_pdf_never_touches_ocr() -> None:
    engine = RecordingEngine([])
    seen: list[str] = []
    result = run_document_intake(
        [("claim.pdf", _pdf_bytes("Jane owes $1000."))],
        extractor=_capturing_extractor(seen),
        engine=engine,
    )
    assert engine.calls == []
    assert isinstance(result, DocumentIntakeResult)
    assert result.search_rounds == 0
    assert result.files[0].text.strip() == "Jane owes $1000."
    assert result.case.claimant_name == "Jane"


def test_blank_pdf_page_goes_through_ocr() -> None:
    engine = RecordingEngine(["OCR TEXT"])
    seen: list[str] = []
    result = run_document_intake(
        [("scan.pdf", _pdf_bytes(None))],
        extractor=_capturing_extractor(seen),
        engine=engine,
    )
    assert len(engine.calls) == 1
    assert "OCR TEXT" in result.files[0].text
    assert "OCR TEXT" in seen[0]


def test_raster_png_goes_through_ocr() -> None:
    engine = RecordingEngine(["IMAGE TEXT"])
    result = run_document_intake(
        [("scan.png", _png_bytes())],
        extractor=_capturing_extractor([]),
        engine=engine,
    )
    assert len(engine.calls) == 1
    assert "IMAGE TEXT" in result.files[0].text


def test_typed_narrative_is_appended_after_document_text() -> None:
    engine = RecordingEngine([])
    seen: list[str] = []
    run_document_intake(
        [("claim.pdf", _pdf_bytes("file text from the PDF"))],
        text="a typed narrative that mentions the dispute",
        extractor=_capturing_extractor(seen),
        engine=engine,
    )
    assert seen
    assert "file text from the PDF" in seen[0]
    assert "typed narrative that mentions the dispute" in seen[0]
    assert seen[0].index("typed narrative") > seen[0].index("file text")


def test_unreadable_corpus_raises() -> None:
    engine = RecordingEngine([])
    with pytest.raises(ValueError, match="no readable text"):
        run_document_intake(
            [("junk.bin", b"\x00\x01\x02")],
            extractor=_capturing_extractor([]),
            engine=engine,
        )
    assert engine.calls == []


def test_no_files_and_no_text_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        run_document_intake([], extractor=_capturing_extractor([]))


def test_per_file_warnings_surface() -> None:
    engine = RecordingEngine([])
    result = run_document_intake(
        [
            ("junk.bin", b"\x00\x01\x02"),
            ("claim.pdf", _pdf_bytes("Jane owes $1000.")),
        ],
        extractor=_capturing_extractor([]),
        engine=engine,
    )
    assert len(result.files) == 2
    assert result.files[0].warnings
    assert isinstance(result.files[0], IngestedFile)
    assert not result.files[1].warnings
    assert result.files[1].text.strip() == "Jane owes $1000."
