"""Endpoint tests for /api/extract-document (no network / no live LLM)."""

from __future__ import annotations

import io

import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
from ocr_engine.base import OCREngine

CANNED_ANSWERS: dict[str, str] = {
    "claimant_name": "John Doe",
    "claimant_nric": "S1234567A",
    "claimant_email": "john@example.com",
    "respondent_name": "Jane Ong",
    "nature_of_dispute": "Contract for sale of goods",
    "claim_amount": "10000",
    "date_of_cause_of_action": "2026-09-02",
    "particulars": "",
}


def _canned_extract(text: str) -> dict[str, str]:
    answers = dict(CANNED_ANSWERS)
    answers["particulars"] = text
    return answers


class EmptyEngine(OCREngine):
    @property
    def name(self) -> str:
        return "empty"

    def recognize(self, image: np.ndarray) -> str:
        return ""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(app_module, "extract_fields", _canned_extract)
    return TestClient(app_module.app)


def _text_pdf_bytes(text: str = "Jane owes John Doe ten thousand dollars for goods.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (500, 300), color=(255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_document_from_text_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/extract-document",
        files={"files": ("claim.pdf", _text_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["field_help"]["claimantName"]["suggestion"] == "John Doe"
    documents = body["documents"]
    assert len(documents) == 1
    assert documents[0]["filename"] == "claim.pdf"
    assert documents[0]["pages"][0]["source"] == "text"
    assert documents[0]["full_text"].startswith("Jane owes")


def test_extract_document_accepts_multiple_files(client: TestClient) -> None:
    files = [
        ("files", ("a.pdf", _text_pdf_bytes("first claim text"), "application/pdf")),
        ("files", ("b.pdf", _text_pdf_bytes("second claim text"), "application/pdf")),
    ]
    response = client.post("/api/extract-document", files=files)
    assert response.status_code == 200, response.text
    assert len(response.json()["documents"]) == 2


def test_extract_document_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/extract-document",
        files={"files": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_extract_document_empty_document_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ocr_engine.service._get_default_engine", lambda: EmptyEngine())
    response = client.post(
        "/api/extract-document",
        files={"files": ("blank.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 422
    assert "No readable text" in response.json()["detail"]


def test_extract_document_ocr_image_uses_ocr_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeEngine(OCREngine):
        @property
        def name(self) -> str:
            return "fake"

        def recognize(self, image: np.ndarray) -> str:
            return "Jane Ong owes John Doe 10000 dollars for a sofa."

    monkeypatch.setattr("ocr_engine.service._get_default_engine", lambda: FakeEngine())
    response = client.post(
        "/api/extract-document",
        files={"files": ("scan.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["documents"][0]["pages"][0]["source"] == "ocr"
    assert "10000" in body["field_help"]["claimAmount"]["suggestion"]
