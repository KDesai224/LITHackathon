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
   - Ingests incident narratives and maps them to the 8 statutory SCT intake fields (Claimant Name, NRIC, Respondent Name, Address, Dispute Nature, Claim Amount, Dispute Date, Statement of Claim).
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
                         │
                         │ HTTP / JSON
                         ▼
[ FastAPI Application (app.py:8743) ]
  ├── GET  /api/health            -> Status & OpenAI key verification
  ├── POST /api/check-tone        -> Tone detection & factual rewrite engine
  ├── POST /api/extract-fields    -> SCT field extraction via OpenAI tool calls
  └── StaticFiles /               -> Serves portal UI, icons, and styles
```

### Backend Components
* **`app.py`**: Async FastAPI application and static asset server.
* **`backend/tone_detector.py`**:
  * **Tier 1 (<5ms local regex rule bank):** Catches generalizations, criminal accusations, insults, and threats offline with zero API dependency.
  * **Tier 2 (LLM Contextual Analyzer):** Enhances with `gpt-4o-mini` via OpenAI-compatible endpoints when an API key is provided.
* **`client_upload.py`**: SCT intake domain model (`SCTCase`) enforcing Decimal currency, ISO dates, and SCT dispute categories.
* **`field_extractor.py`**: OpenAI-compatible tool call wrapper for structured claim intake extraction.
* **`backend/field_evidence.py`**: Evidence provenance, citation verification, and 5-component confidence scoring.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python **3.11+** installed.
- Git.

### 2. Install Dependencies
Run the following in your terminal:
```bash
pip install fastapi uvicorn pydantic python-dotenv requests
```
*(Or if using pyproject.toml: `pip install -e .`)*

### 3. (Optional) Configure OpenAI API Key
Create a `.env` file in the project root:
```env
OPENAI_API_KEY=your_openai_api_key_here
# Optional overrides:
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini
```
> **Note:** Even without an API key, the app runs completely offline in fallback mode using Tier 1 heuristics and pre-configured responses.

### 4. Start the Application
```bash
python app.py
```

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

## 🔬 Running Unit Tests

Run the automated test suite with Python's built-in test runner:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

All tests for tone detection, heuristic fallbacks, and evidence scoring will execute.

---

## 📄 Key Documentation
- [PRD.md](file:///C:/Users/kiara_qi2p9x4/LITHackathon/PRD.md) — Complete product requirements and statutory tribunal specifications.
- [DESIGN.md](file:///C:/Users/kiara_qi2p9x4/LITHackathon/stitch_self_representation_legal_filing_assistant-2/DESIGN.md) — Civic Justice Portal design system tokens, typography, and component specifications.
