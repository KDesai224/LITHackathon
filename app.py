"""ClaimReady / ClaimBuddy FastAPI Server.

Serves the mock portal frontend and exposes REST APIs for:
1. Form Field Extraction (/api/extract-fields)
2. Hostile Language Detection & Protective Guidance (/api/check-tone)
3. Full Claim Data Validation (/api/validate-claim)
4. Pre-Filing Claim PDF Generation (/api/generate-pdf)
5. Health check (/api/health)
6. PDF / scanned-document ingestion and extraction (/api/extract-document)
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.pdf_generator import generate_prefiling_pdf
from backend.tone_detector import ToneCheckResult, check_tone
from sct_intake import FieldExtractionError, SCTCase, extract_fields

# Load local configuration before health checks or request handlers inspect it.
load_dotenv()

PORT = 8743
STATIC_ROOT = Path(__file__).resolve().parent / "frontend" / "claimready"

DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}
MAX_DOCUMENT_FILES = 10
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 250_000

_FIELD_META: dict[str, tuple[str, str, str]] = {
    "claimantName": ("claimant_name", "Your full name (Claimant)", "Enter your name as it appears on your identification document."),
    "claimantId": ("claimant_nric", "Your NRIC / FIN", "Enter your NRIC or FIN exactly as shown on your identification document."),
    "claimantEmail": ("claimant_email", "Email address", "Enter a valid email address where court service notices can reach you."),
    "respondentName": ("respondent_name", "Respondent's full name or business name", "This identifies the person or business you are making the claim against."),
    "respondentAddress": ("", "Respondent's address for service", "Enter an address where the respondent can receive claim papers."),
    "claimNature": ("nature_of_dispute", "Nature of claim", "Choose the claim category that best describes your dispute."),
    "claimAmount": ("claim_amount", "Amount you want to claim", "Enter the amount you are asking the respondent to repay."),
    "claimDate": ("date_of_cause_of_action", "Date the dispute arose", "Enter the date the event giving rise to your claim happened."),
    "claimStatement": ("particulars", "Brief statement of claim", "Summarise what happened and what you are asking the Tribunal to order."),
}

_UI_NATURES = {
    "Contract for sale of goods": "Contract for Sale of Goods",
    "Contract for provision of services": "Contract for Provision of Services",
    "Damage to property": "Damage to Property",
    "Lease not exceeding two years": "Tenancy / Residential Lease",
}

NRIC_PATTERN = re.compile(r"^[STFGMstfgm]\d{7}[A-Za-z]$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _find_evidence(value: str, passages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Find a short, exact evidence quote and its document/page citation."""
    value = value.strip()
    if not value:
        return None, None
    for passage in passages:
        text = str(passage.get("text") or "")
        match = re.search(re.escape(value), text, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            quote = " ".join(text[start:end].split())
            document = passage.get("document")
            page = passage.get("page")
            citation = f"{document}, page {page}" if document and page else str(document or "")
            return quote, citation or None
    return None, None


def build_field_help(
    answers: dict[str, Any], *, passages: list[dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    """Translate extractor fields into UI help fields with grounded evidence."""
    source = str(
        answers.get("source")
        or "Claim narrative provided by the user (no document-page citation available)"
    ).strip()
    result: dict[str, dict[str, Any]] = {}
    for field_id, (answer_key, title, explanation) in _FIELD_META.items():
        suggestion = str(answers.get(answer_key) or "").strip() if answer_key else ""
        if field_id == "claimNature" and suggestion:
            suggestion = _UI_NATURES.get(suggestion, suggestion)
        if field_id == "claimDate" and suggestion:
            suggestion = suggestion[:10]
        quote, citation = _find_evidence(suggestion, passages or [])
        result[field_id] = {
            "label": title,
            "explanation": explanation,
            "suggestion": suggestion,
            "available": bool(suggestion),
            "quote": quote,
            "citation": citation,
            "source": source,
            "why_this_helps": explanation,
            "requires_confirmation": True,
        }
    return result


# --------------------------------------------------------------------------- #
# Request / Response Models & Validation
# --------------------------------------------------------------------------- #

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=250_000, description="Claim narrative or incident text")


class ToneCheckRequest(BaseModel):
    text: str = Field(..., description="Draft text from free-form fields such as statement of claim")


class ClaimFormData(BaseModel):
    claimant_name: str = ""
    claimant_nric: str = ""
    claimant_email: str = ""
    respondent_name: str = ""
    respondent_address: str = ""
    nature_of_dispute: str = ""
    claim_amount: str = ""
    date_of_cause_of_action: str = ""
    particulars: str = ""
    reference_number: str | None = None


def validate_claim_data(data: ClaimFormData) -> dict[str, str]:
    """Validate all claim form fields and return a mapping of field_name -> error_message."""
    errors: dict[str, str] = {}

    # 1. Claimant Name
    name = data.claimant_name.strip()
    if not name:
        errors["claimantName"] = "Full name is required as shown on your NRIC/Passport."
    elif len(name) < 2:
        errors["claimantName"] = "Name must be at least 2 characters long."

    # 2. Claimant NRIC / FIN
    nric = data.claimant_nric.strip().upper()
    if not nric:
        errors["claimantId"] = "NRIC / FIN is required."
    elif not NRIC_PATTERN.match(nric):
        errors["claimantId"] = "Enter a valid NRIC/FIN format (e.g. S1234567A)."

    # 3. Claimant Email
    email = data.claimant_email.strip()
    if not email:
        errors["claimantEmail"] = "Email address is required for court service notices."
    elif not EMAIL_PATTERN.match(email):
        errors["claimantEmail"] = "Enter a valid email address (e.g. name@example.com)."

    # 4. Respondent Name
    resp_name = data.respondent_name.strip()
    if not resp_name:
        errors["respondentName"] = "Respondent full name or registered business name is required."

    # 5. Respondent Address
    resp_addr = data.respondent_address.strip()
    if not resp_addr:
        errors["respondentAddress"] = "Respondent address for service of claim papers is required."

    # 6. Nature of Dispute
    nature = data.nature_of_dispute.strip()
    if not nature:
        errors["claimNature"] = "Please select a claim category."

    # 7. Claim Amount (Strict numeric validation)
    amt_str = data.claim_amount.strip().replace("$", "").replace(",", "")
    if not amt_str:
        errors["claimAmount"] = "Claim amount is required."
    else:
        # Reject if letters or invalid symbols are present
        if re.search(r"[^\d.]", amt_str):
            errors["claimAmount"] = "Invalid amount. Enter numbers only (no letters or symbols)."
        else:
            try:
                amt = Decimal(amt_str)
                if amt <= 0:
                    errors["claimAmount"] = "Claim amount must be greater than $0.00."
                elif amt > 30000:
                    errors["claimAmount"] = "Small Claims Tribunal jurisdiction is capped at $30,000 max (with consent, or $20,000 standard)."
            except InvalidOperation:
                errors["claimAmount"] = "Invalid numerical format. Enter numbers only (e.g. 4500)."

    # 8. Dispute Date (Strict calendar & statute of limitations validation)
    date_str = data.date_of_cause_of_action.strip()
    if not date_str:
        errors["claimDate"] = "Date the dispute arose is required."
    else:
        try:
            parsed_date = datetime.fromisoformat(date_str[:10]).date()
            today = datetime.now(UTC).date()
            two_years_ago = today - timedelta(days=730)
            if parsed_date > today:
                errors["claimDate"] = "Dispute date cannot be in the future."
            elif parsed_date < two_years_ago:
                errors["claimDate"] = "SCT claims must be filed within 2 years from the date the dispute arose (SCT Act s.5(4))."
        except ValueError:
            errors["claimDate"] = "Invalid date format. Please use YYYY-MM-DD."

    # 9. Particulars / Statement of Claim
    stmt = data.particulars.strip()
    if not stmt:
        errors["claimStatement"] = "Please provide a brief statement describing what happened."
    elif len(stmt) < 10:
        errors["claimStatement"] = "Statement must be at least 10 characters long to explain the dispute."

    return errors


# --------------------------------------------------------------------------- #
# FastAPI Application
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="ClaimBuddy / ClaimReady API",
    description="Backend services for AI-assisted Small Claims Tribunal preparation",
    version="1.0.0",
)

# CORS is only needed when the frontend is served from a different origin.
# By default the app serves both the API and the static site (same origin), so
# no CORS middleware is added. Set CORS_ORIGINS to a comma-separated allow-list
# when hosting the frontend separately.
_cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "chat_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "chat_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "services": {
            "intake": "registered",
            "ocr": "registered",
            "tone": "registered",
            "pdf": "registered",
        },
        "has_openai_key": bool(os.getenv("OPENAI_API_KEY", "").strip()),
    }


@app.get("/api")
def api_catalog() -> dict[str, Any]:
    """Return the local service catalog used by demos and API clients."""
    return {
        "service": "claimready-api",
        "version": app.version,
        "endpoints": {
            "health": {"method": "GET", "path": "/api/health"},
            "extract_fields": {"method": "POST", "path": "/api/extract-fields"},
            "extract_document": {"method": "POST", "path": "/api/extract-document"},
            "check_tone": {"method": "POST", "path": "/api/check-tone"},
            "validate_claim": {"method": "POST", "path": "/api/validate-claim"},
            "generate_pdf": {"method": "POST", "path": "/api/generate-pdf"},
        },
    }


def _field_help_from_text(
    text: str,
    *,
    source: str | None = None,
    passages: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run field extraction over a claim narrative and map to UI help fields."""
    case = SCTCase.from_text(text, extractor=extract_fields, source=source)
    return build_field_help(case.to_dict(), passages=passages or [{"text": text}])


def _field_help_or_http_raise(
    text: str,
    *,
    source: str | None = None,
    passages: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run extraction, translating known failures into HTTP errors."""
    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A non-empty claim narrative is required.",
        )
    try:
        return _field_help_from_text(text, source=source, passages=passages)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FieldExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to analyse the claim narrative.",
        ) from exc


def _serialize_document_result(document: Any) -> dict[str, Any]:
    """Serialise an ocr_engine DocumentResult for the API response."""
    return {
        "filename": document.filename,
        "full_text": document.full_text,
        "pages": [
            {"page": page.page, "text": page.text, "source": page.source}
            for page in document.pages
        ],
        "warnings": list(document.warnings),
    }


def _read_upload(upload: UploadFile) -> bytes:
    """Read an uploaded file, enforcing the per-file size cap."""
    data = upload.file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{upload.filename}' exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB limit.",
        )
    return data


def _document_extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files must have a filename with an extension.",
        )
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in DOCUMENT_EXTENSIONS:
        allowed = ", ".join(sorted(DOCUMENT_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '.{extension}'. Allowed: {allowed}.",
        )
    return extension


@app.post("/api/extract-fields")
def api_extract_fields(payload: ExtractRequest) -> dict[str, Any]:
    return {"field_help": _field_help_or_http_raise(payload.text)}


@app.post("/api/extract-document")
def api_extract_document(
    files: list[UploadFile] = File(...),  # noqa: B008 - FastAPI multipart marker
    text: str = Form(""),  # optional typed narrative appended to the OCR text
) -> dict[str, Any]:
    """Ingest PDFs and scanned images, then extract SCT case fields.

    Born-digital PDFs use their embedded text layer; scanned pages and raster
    images are recognised by the bundled rapidocr engine. The combined text is
    run through the same field-extraction pipeline as :func:`api_extract_fields`.
    An optional ``text`` form field may carry typed incident narrative that is
    appended after the document text.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required.",
        )
    if len(files) > MAX_DOCUMENT_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {MAX_DOCUMENT_FILES} files per request.",
        )
    narrative = text.strip()
    if len(narrative) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Typed text exceeds the {MAX_TEXT_CHARS // 1000}K character limit.",
        )

    from ocr_engine import OCRUnavailableError, extract_text_from_bytes

    documents = []
    passages: list[dict[str, Any]] = []
    filenames: list[str] = []
    full_texts: list[str] = []
    for upload in files:
        filename = upload.filename or "document"
        filenames.append(filename)
        _document_extension(upload.filename)
        content = _read_upload(upload)
        try:
            result = extract_text_from_bytes(content, filename)
        except OCRUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"OCR engine unavailable: {exc}",
            ) from exc
        documents.append(_serialize_document_result(result))
        if result.full_text.strip():
            full_texts.append(result.full_text)
        passages.extend(
            {"document": filename, "page": page.page, "text": page.text}
            for page in result.pages
            if page.text.strip()
        )

    if narrative:
        full_texts.append(narrative)
    combined = "\n\n".join(full_texts).strip()
    if not combined:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text was found in the uploaded document(s) or typed narrative.",
        )

    source = ", ".join(filenames)
    return {
        "field_help": _field_help_or_http_raise(combined, source=source, passages=passages),
        "documents": documents,
    }


@app.post("/api/check-tone")
def api_check_tone(payload: ToneCheckRequest) -> dict[str, Any]:
    """Check text for hostile, extreme, or generalizing wording."""
    result: ToneCheckResult = check_tone(payload.text)
    return result.to_dict()


@app.post("/api/validate-claim")
def api_validate_claim(payload: ClaimFormData) -> dict[str, Any]:
    """Validate all claim form fields and check tone of the statement."""
    errors = validate_claim_data(payload)
    tone_result = check_tone(payload.particulars) if payload.particulars.strip() else None

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "tone": tone_result.to_dict() if tone_result else None,
    }


@app.post("/api/generate-pdf")
def api_generate_pdf(payload: ClaimFormData) -> Response:
    """Validate claim data and generate a downloadable SCT Pre-Filing Claim Summary PDF."""
    errors = validate_claim_data(payload)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Please correct the form errors before generating the PDF.", "errors": errors},
        )

    try:
        pdf_bytes = generate_prefiling_pdf(payload.model_dump())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {exc}",
        ) from exc

    ref = payload.reference_number or f"DRAFT-{datetime.now(UTC).strftime('%Y%m%d')}"
    filename = f"SCT_PreFiling_Claim_{ref}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "X-Reference-Number": ref,
        },
    )


# Redirect root to dummy-website.html
@app.get("/", include_in_schema=False)
def index_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dummy-website.html")


# Mount static website files
if STATIC_ROOT.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")


def main() -> None:
    print(f"Starting ClaimReady FastAPI server on http://127.0.0.1:{PORT}/dummy-website.html")
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=True)


if __name__ == "__main__":
    main()
