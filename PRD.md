# Product Requirements Document (PRD)
## ClaimBuddy — AI-Assisted Claim Preparation Overlay for the Small Claims Tribunal (SCT)

---

## 1. Overview

**Product name:** ClaimBuddy

**One-line description:** ClaimBuddy is an AI-assisted overlay designed to sit on top of the MinLaw / e-Litigation portal, helping self-represented persons (SRPs) prepare Small Claims Tribunal (SCT) filings accurately, safely, and in line with the Courts' Guide on the Use of Generative Artificial Intelligence Tools by Court Users.

**Hackathon scope note:** Since we cannot integrate with or scrape the real MinLaw website, this build is a **standalone mock replica of the MinLaw claim-filing portal**, with ClaimBuddy functioning as an overlay/side-panel within that mock environment. In production, this would be designed as a browser extension or embedded panel within the real e-Litigation portal — this is described as the production vision, not something built for the hackathon.

---

## 2. Problem Statement

Self-represented persons (SRPs) in the Small Claims Tribunals (SCT) increasingly turn to publicly available generative AI (GenAI) tools for help navigating the claims process. Without appropriate guidance, they risk:
- Misunderstanding relevant information
- Filing incomplete or poorly organised claims
- Having their existing assumptions reinforced rather than objectively assessed
- Using language or making statements that could carry legal consequences without realising it

## 3. Goals

- Help SRPs understand and navigate the SCT claims process in plain language
- Ground all AI guidance in the user's own uploaded documents (reduce hallucination)
- Flag potentially harmful or hostile language before submission (reduce legal risk to the user)
- Ensure every AI suggestion is transparent, sourced, and requires active user review (responsible AI use, in line with the Courts' Guide)
- Reduce time and confusion for SRPs preparing a claim without a lawyer

## 4. Non-Goals (Out of Scope for Hackathon Build)

- Real integration with MinLaw / e-Litigation (mocked instead)
- Real SingPass authentication (mocked UI/flow only)
- Legally binding or court-submittable output — this is a preparation aid, not a filing system
- Google Calendar integration is a **stretch goal only**, not a committed feature

---

## 5. User Flow & Functional Requirements

### 5.1 Login (SingPass, mocked)
- First screen: mock SingPass login button/flow.
- On "successful login," user proceeds to the personal information entry screen.

### 5.2 Personal Information Entry
- User enters personal details required for the claim (name, contact info, NRIC, address, etc.).
- All personal information entered is **hashed** by the overlay before storage, for the purposes of this hackathon build.
- A short disclosure banner is shown here: this tool uses AI to assist with claim preparation, does not replace legal advice, and all AI suggestions must be reviewed by the user before filing.

### 5.3 ClaimBuddy Activation
- A persistent "ClaimBuddy" button is visible once the user is in the claim-filing portal.
- Clicking it opens a **side panel** (does not navigate away from the form) where the user can:
  - Upload supporting documents (contracts, receipts, correspondence, etc.)
  - Receive dumbed-down, plain-language guidance on how the SCT claims process works and what filing a claim involves

### 5.4 Document Ingestion
- Uploaded documents are ingested and chunked, then embedded for retrieval.
- These embeddings are used to ground later tooltip suggestions and citations (see 5.5).

### 5.5 Guided Form-Fill with Tooltips
- As the user fills out each field on the claim form, an info/tooltip icon sits next to each field.
- On hover, the tooltip shows:
  1. What should be filled into this field
  2. A short quoted excerpt (one line or a few words) from the user's uploaded document that supports the suggestion
  3. A brief explanation of *why* this information should be filled in this way
- Tooltips are advisory only — the user must manually accept/type the value; nothing is auto-filled silently.

### 5.6 Hostile & Extreme Language Detection (Protective Guidance)
- **Non-Punitive Posture:** Framed as protective guidance for the user's own claim under the Singapore Courts' GenAI guidelines, not as punitive content moderation or blocking.
- **Trigger & Visual Alert:** On free-form text entry (e.g. Field 8 "Brief statement of claim" or incident narrative), the system evaluates phrasing in real-time or on blur.
  - When flagged, the input box visually highlights with an amber warning border.
  - An inline advisory card appears prompting: *"Are you sure you wish to proceed with this wording?"*
- **Empirical Court Statistics & Grounded Disclaimer:**
  - Emphasizes real State Courts / SCT procedural realities: over 11,000 cases are filed annually in the SCT, and all claims proceed to mandatory Consultation (mediation) with a Registrar.
  - States: *"Court mediation data shows that personal insults and generalizations drastically reduce your chances of an amicable settlement and weaken your credibility before the Magistrate."*
  - Clarifies that generalizations regarding age, character, or demographics have 0% legal relevance to civil debt or breach of contract and risk being deemed scandalous or vexatious.
- **1-Click Factual Alternative (Human in Control):**
  - Generates a court-admissible factual rewrite that preserves the user's actual grievance (dates, amounts paid, failed delivery, lack of refund).
  - Offers two explicit actions:
    1. `[ Use recommended fix ]`: Automatically replaces the inflammatory text with the neutral statement and clears the warning.
    2. `[ Proceed anyway ]`: Lets the claimant submit their original wording without being blocked.
- **Two-Tier Engine Architecture:**
  - **Tier 1 (Instant <5ms Heuristics):** Zero-latency rule bank catching group/ageist generalizations, criminal labels (`thief`, `scammer`), abuse (`useless`, `idiot`), and threats (`pay or else`). Guarantees offline live demo stability.
  - **Tier 2 (LLM Contextual Analyzer):** Evaluates semantic nuances and synthesizes custom factual rewrites using `gpt-4o-mini` via an OpenAI-compatible API.

### 5.7 Post-Fill Output
- Once the form is completed, ClaimBuddy presents:
  - Important upcoming court dates/deadlines relevant to the claim
  - Downloadable templates: Affidavit of Evidence-in-Chief, and the relevant SCT claim/originating application template
- **Stretch goal (not committed):** option to push key dates to Google Calendar via a plug-in/integration.

### 5.8 End-to-End Strict Data Validation (Frontend & Backend)
- **Zero Hallucination / Mistake Prevention:** Pre-filing form fields undergo synchronous real-time frontend validation (on keystroke and blur) paired with strict server-side validation (`POST /api/validate-claim`).
- **Validation Rules Enforced:**
  1. **Claim Amount:** Numbers only (strictly rejects alphabet characters and non-numeric symbols); must be > $0.00; capped at statutory limit of $30,000 max.
  2. **Dispute Date:** Valid calendar date; cannot be in the future; must be within 2 years from today pursuant to Section 5(4) of the Small Claims Tribunals Act (limitation period).
  3. **Claimant Email:** Strict RFC 5322 regex pattern check for valid court electronic notice delivery.
  4. **Claimant NRIC/FIN:** Valid Singapore NRIC/FIN format check (`^[STFGMstfgm]\d{7}[A-Za-z]$`).
  5. **Particulars / Statement:** Minimum 10 characters explaining factual basis; evaluated simultaneously for hostile or defamatory language.
- **Progress Tracking:** Submissions and PDF downloads are gated until all 8 required fields pass validation without errors.

### 5.9 Official Pre-Filing Claim Summary PDF Generator
- **Publication-Grade PDF Output:** Users on both Page 2 (pre-filing form) and Page 3 (after-filing confirmation) can generate and download an official SCT Form 1 Pre-Filing Summary PDF via `POST /api/generate-pdf`.
- **Styling & Legal Standard:** Built via `reportlab` with judicial maroon accents (`#8B1D3D`), structured two-column party particulars, financial summary tables, dispute timeline, factual statement, procedural consultation checklist, and Singapore Courts GenAI guideline disclosure banners.

---

## 6. Key Design Principles

- **Grounding over generation:** every AI suggestion should be traceable to either the user's own uploaded documents or known SCT procedural information — not freely generated.
- **Transparency by default:** every tooltip cites its source and reasoning; nothing is presented as an unexplained answer.
- **Human stays in control:** the user must actively accept, edit, or reject every AI suggestion — no silent auto-fill.
- **Protective, not punitive tone:** guidance reads as "here is how this language may harm your case and how to protect your claim", never as a scolding or a hard block.
- **Compliance with the Courts' Guide on the Use of Generative Artificial Intelligence Tools by Court Users:** disclosure banners, no fabricated legal citations or fake statistics, and clear distinction between AI-assisted content and the user's own submission.

---

## 7. Tech Stack & Implemented Architecture

**Language:** Python (backend/AI logic) with vanilla HTML5/JavaScript + Tailwind CSS for the mock portal UI.

| Layer | Implemented Component | Notes |
|---|---|---|
| Frontend | HTML5 + Tailwind CSS + Vanilla JS (`frontend/claimready/dummy-website.html` + `claimready-overlay.js`) | Replicates MinLaw/Judiciary Civic Portal with ClaimReady companion overlay |
| Backend/API | **FastAPI** (`app.py`) on Python 3.11+ / Uvicorn | Async REST server serving static assets and AI API endpoints on port 8743 |
| Hostile Language Detector | Two-Tier Engine (`backend/tone_detector.py` + frontend regex bank) | Tier 1 local regex rule bank + Tier 2 `gpt-4o-mini` LLM analyzer + mediation stats |
| Data Validation Engine | Dual Frontend & Backend Validator (`app.py:validate_claim_data`) | Rejects letters in number boxes, future dates, >2yr expired dates, invalid NRIC/email |
| Pre-Filing PDF Generator | **ReportLab 5.0.1** (`backend/pdf_generator.py`) | Compiles official Form 1 Pre-Filing Claim Summary with procedural checklists |
| Case Domain Orchestrator | `client_upload.py` (`SCTCase`) | Validates 4 closed SCT dispute categories, ISO 8601 dates, Decimal currency |
| Field Extraction Engine | `field_extractor.py` (`submit_sct_fields`) | OpenAI-compatible tool calling forcing structured JSON extraction |
| Evidence & Audit Scorer | `backend/field_evidence.py` | Validates citations, computes 5-component confidence scores, enforces safety caps |
| Hashing (personal info) | Python `hashlib` (SHA-256) | Sanitizes PII before storage/logging |
| Testing Suite | `unittest` + `fastapi.testclient` (`tests/test_*.py`) | Comprehensive offline unit & endpoint integration tests |

### REST Endpoints Summary:
- `GET /api/health`: Confirms server status and LLM API key detection.
- `POST /api/extract-fields`: Ingests incident text and outputs 8 grounded field suggestions with explanations.
- `POST /api/check-tone`: Analyzes statement text for hostility, returning amber warning flags, mediation disclaimer, and factual rewrite.
- `POST /api/validate-claim`: Validates all form inputs and flags syntax, logic, or tone discrepancies.
- `POST /api/generate-pdf`: Validates inputs and returns a streaming downloadable PDF file (`application/pdf`).
- `GET /`: Redirects directly to `/dummy-website.html`.

---

## 8. Success Metrics (for Demo/Judging Purposes)

- End-to-end flow works live: login → personal info → document upload → tooltip-guided form fill → hostile language flag triggers correctly → PDF summary downloaded.
- At least one tooltip demonstrably cites a real excerpt from an uploaded document.
- Hostile language detection correctly triggers on scripted "aggressive/generalizing" input (e.g. *"i want my money back these young people are always like this useless money stealing youth"*), with zero latency and robust client-side fallback.
- Pre-filing PDF generates within <500ms with official courtroom styling and complete data summary.
- Form inputs reject invalid formats (letters in currency, future dates, invalid emails) with explicit helpful inline guidance.
- Clear, visible framing throughout the UI that AI suggestions are advisory and require user review (ties back to responsible-AI-use goal).

---

## 9. Status of Open Questions

- [x] **Hostile Language Legal Repercussions & Disclaimer:** Settled on grounded court mediation statistics (over 11,000 cases filed annually, mandatory consultation, loss of settlement chances and magistrate credibility) rather than speculative penalties.
- [x] **Web & API Framework:** Implemented with FastAPI + Uvicorn for clean async JSON endpoints and static file serving.
- [x] **SCT Claim Form Fields:** Form replicated with 8 core statutory fields matching State Courts e-Litigation practice.
- [x] **Official Claim Summary PDF Generation:** Implemented using ReportLab for client preparation before SCT consultation.
- [x] **Strict Data Validation:** Comprehensive frontend & backend validation implemented.
- [ ] Final decision on Google Calendar integration (stretch goal).
- [ ] Confirm final LLM model/version to cite in any public-facing pitch materials.
