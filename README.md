# ClaimBuddy / ClaimReady
### AI-Assisted Claim Preparation Overlay for Singapore Small Claims Tribunals (SCT)

ClaimBuddy (represented by the **ClaimReady** prototype) is an AI-assisted companion designed to help Self-Represented Persons (SRPs) prepare Small Claims Tribunal filings safely, accurately, and in compliance with the **Singapore Courts' Guide on the Use of Generative Artificial Intelligence Tools by Court Users**.

---

## 🌟 Key Features

1. **Hostile Language Protection & Factual Rewriting (Free-Text Fields)**
   - **Non-punitive protective posture:** Does not censor or block the user; instead, warns them of legal risks to their own case.
   - **Grounded mediation data:** Surfaces real Singapore State Courts SCT procedural realities (over 11,000 claims filed annually, all undergoing mandatory mediation/consultation) where personal hostility harms settlement rates and magistrate credibility.
   - **1-Click Factual Alternative:** Strips out emotional attacks and ageist/group generalizations while strictly preserving the claimant's underlying legal grievance.
   - **Human in Control:** Explicit choice between adopting the recommended factual wording or proceeding with original text.

2. **Automated SCT Field Extraction & Grounded Tooltips**
   - Ingests incident narratives and uploaded PDFs/scans and maps them to the SCT intake fields (Claimant Name, NRIC, Email, Respondent Name, Address, Dispute Nature, Claim Amount, Dispute Date, Statement of Claim).
   - Validates dispute categories against the closed statutory set: *Contract for Sale of Goods*, *Provision of Services*, *Damage to Property*, *Tenancy ≤ 2 years*.

3. **Civic Justice Design System (DESIGN.md)**
   - Built to institutional judiciary standards: Singapore judicial maroon (`#8B1D3D`), slate neutrals, Public Sans typography, 4px soft corners, and high contrast.
   - Amber alert tokens (`#D97706`) for advisory guidance.

4. **Self-Contained Floating Guide Overlay (`claimready-overlay.js`)**
   - Standalone widget providing "Find my route" triaging and an "After filing" procedural checklist (service of documents, registrar consultation prep).

---

## 🏗️ Architecture

```
[ Frontend: dummy-website.html + claimready-overlay.js ]
          │  same origin, relative /api calls (no CORS needed)
          ▼
[ FastAPI Application (app.py:8743) ]
  ├── GET  /api/health              -> Status & OpenAI key verification
  ├── POST /api/extract-fields      -> SCT field extraction from typed text
  ├── POST /api/extract-document    -> PDF/scanned-image OCR + field extraction
  ├── POST /api/check-tone          -> Tone detection & factual rewrite engine
  ├── POST /api/validate-claim      -> Full form validation (fields + tone)
  ├── POST /api/generate-pdf        -> Pre-filing PDF with reference number
  └── StaticFiles /                 -> Serves portal UI, icons, and styles
```

### Backend Components
* **`app.py`**: FastAPI application, static asset server, and the same-origin API the served
  frontend calls.
* **`backend/tone_detector.py`**:
  * **Tier 1 (<5ms local regex rule bank):** Catches generalizations, criminal accusations, insults, and threats offline with zero API dependency.
  * **Tier 2 (LLM Contextual Analyzer):** Enhances via an OpenAI-compatible endpoint (e.g. DeepSeek) when an API key is provided in `.env`.
* **`sct_intake/`**: SCT intake domain package (`SCTCase`) enforcing Decimal currency, ISO dates,
  and SCT dispute categories; config, retrieval/embeddings, and the tool-call extraction wrapper.
  (Top-level `client_upload.py` / `field_extractor.py` are compat shims re-exporting it.)
* **`ocr_engine/`**: Cross-platform document ingestion (PyMuPDF text layer + rapidocr/onnxruntime
  OCR for scanned pages).
* **`backend/field_evidence.py`**: Evidence provenance, citation verification, and 5-component confidence scoring.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python **3.11+** (the project is managed with [uv](https://docs.astral.sh/uv/)).
- Git.

### 2. Install Dependencies
```bash
uv sync --dev
```

### 3. Configure the AI endpoint
Create a `.env` file in the project root (copy `.env.example`). Example for DeepSeek:
```env
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-...
OPENAI_MODEL=deepseek-v4-flash
# Optional: comma-separated origins allowed when the frontend is hosted separately:
# CORS_ORIGINS=http://localhost:3000
```
> **Note:** The app runs and the demo UI works without a key for the tone heuristics and OCR
> paths, but field extraction and PDF generation need a working key.

### 4. Start the Application
```bash
uv run python app.py
```
or double-click `stitch_self_representation_legal_filing_assistant-2/run-demo.command` (macOS).

Open your browser to:
👉 **[http://127.0.0.1:8743/dummy-website.html](http://127.0.0.1:8743/dummy-website.html)**
*(or simply [http://127.0.0.1:8743](http://127.0.0.1:8743))*

Interactive API documentation (Swagger UI) is available at:
👉 **[http://127.0.0.1:8743/docs](http://127.0.0.1:8743/docs)**

---

## 🧪 Demo Walkthrough

The whole demo runs from the single **Pre-Filing Assessment** page: a floating
**ClaimReady** widget (bottom-right of the page) drives route triage, document
upload, and the after-filing checklist. Follow the exact click-path in
[`scripts/manual-acceptance.md`](scripts/manual-acceptance.md) for a live,
end-to-end rehearsal.

### Scenario 1: Find my route, auto-fill & per-field help
1. On the page, open the floating **ClaimReady** guide and choose
   **"Let us approximate your route for you"**.
2. In **"Tell us briefly what happened"**, describe the dispute — as typed text,
   attached documents, or both:
   ```
   I paid ABC Renovations $3,500 on 15 February 2025 to renovate my bathroom.
   After taking the deposit they abandoned the work and have not refunded me.
   ```
   Optionally click **Attach documents** to add PDFs or photos. Born-digital
   PDFs are read from their text layer; scanned pages go through the built-in
   OCR engine.
3. Click **"Get an approximate route"**. The widget calls the live extraction
   service and returns a *suggestion* readout — e.g. it may flag this as a
   **Contract for Provision of Services** dispute under the Small Claims
   Tribunal — plus the other fields it spotted. It is framed as a starting
   point only, with a link to the official eligibility rules.
4. Click **"Continue to pre-filing form"**. The form opens with fields the
   assistant is confident about **already filled**; anything you typed yourself
   is never overwritten.
5. Click the **(i)** info icon beside any question to open its help popup: the
   suggested value and its source, or an honest *"No suggestion is available
   yet"* state — citations are never fabricated. **Use this suggestion** applies
   the value to the field.
6. (Optional) After clicking **Save answers**, use **Add more documents** to
   reopen the widget's upload panel with everything already attached preserved;
   **Continue to questionnaire** restores your saved answers and merges any new
   suggestions.

### Scenario 2: Hostile-language protection & the PDF hand-off
1. In the Pre-Filing Form, replace the **9. Brief statement of claim** wording
   with an angry, generalising draft:
   ```
   These young people are always like this useless money stealing youth — I gave
   them a $1,200 deposit for a sofa in January and they never delivered it or
   refunded me.
   ```
   Complete the remaining fields (auto-filled values or typed) so all 9 show as
   done — only then does **Submit** appear.
2. Click **Submit**. The form is validated against the backend rules first; any
   problems (NRIC/FIN format, amount within SCT limits, 2-year limitation, …)
   open a *"Please review the form"* dialog.
3. A statement that trips the hostile-tone check raises an **amber advisory**:
   *"Your statement may read as hostile or escalating."* You stay in control:
   - **Revise statement** — dismiss the advisory and edit your own wording, or
   - **Use the suggested wording** — swap in the factual, court-admissible
     rewrite, or
   - **Continue anyway** — keep your original wording and proceed.
4. Once the statement is clean (or you continue anyway), the **pre-filing PDF**
   downloads and the page moves to the After-Filing screen, which shows the
   **server-generated reference number** (taken from the PDF response's
   `X-Reference-Number` header — never a mocked `CLAIMREADY-DEMO-…` value).
5. Click **"Show me what to do next"** to reopen the widget in its after-filing
   mode: a service-of-documents checklist (serve within 7 days, keep proof,
   file the Declaration of Service) with links to the official guidance.

---

## 🔬 Running Tests

Run the automated test suite with uv + pytest:
```bash
uv run pytest            # fast unit + endpoint tests
uv run pytest -m slow    # embedding model + real-OCR integration tests (CI runs these on push)
```

---

## 📄 Key Documentation
- [PRD.md](PRD.md) — Complete product requirements and statutory tribunal specifications.
- [DESIGN.md](stitch_self_representation_legal_filing_assistant-2/DESIGN.md) — Civic Justice Portal design system tokens, typography, and component specifications.
- [scripts/manual-acceptance.md](scripts/manual-acceptance.md) — step-by-step demo click-path and curl smoke tests.
