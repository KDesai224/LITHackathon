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

### Scenario 1: Test the Hostile Language Detector
1. Open the portal and click **"Start Assessment"** to navigate to Page 2 (Pre-filing Claim Form).
2. Scroll to **Field 8 ("Brief statement of claim")**.
3. Enter or paste an aggressive or generalizing draft:
   ```
   i want my money back these young people are always like this useless money stealing youth.
   ```
4. Observe the intervention:
   - The text area activates an **amber warning border**.
   - An advisory box slides in: *"Are you sure you wish to proceed with this wording?"*
   - Real court mediation statistics explain the risk to the claimant's case.
   - Click **"Use recommended fix"** to instantly replace the statement with an objective, court-admissible version!

### Scenario 2: Test Field Extraction
1. On Page 1, type an incident description:
   ```
   I hired ABC Renovations on 15 Feb 2025 and paid $3,500. They abandoned work and haven't refunded.
   ```
2. Click **"Start Assessment"**.
3. View the generated form fields and click any `(i)` info icon to view the source excerpts and citations.

---

## 🔬 Running Tests

Run the automated test suite with uv + pytest:
```bash
uv run pytest            # fast unit + endpoint tests
uv run pytest -m slow    # embedding model + real-OCR integration tests (CI runs these on push)
```

---

## 📄 Key Documentation
- [PRD.md](file:///C:/Users/kiara_qi2p9x4/LITHackathon/PRD.md) — Complete product requirements and statutory tribunal specifications.
- [DESIGN.md](file:///C:/Users/kiara_qi2p9x4/LITHackathon/stitch_self_representation_legal_filing_assistant-2/DESIGN.md) — Civic Justice Portal design system tokens, typography, and component specifications.
