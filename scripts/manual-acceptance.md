# Manual acceptance checklist — ClaimReady pilot

Run against a live server started from the repo root:

```bash
uv run python app.py   # then open http://127.0.0.1:8743/dummy-website.html
```

Requires a working `.env` with `OPENAI_API_KEY` (and friends) for the live
extraction / PDF steps. Tone heuristics and OCR work without it.

## Click path (in the browser)

1. **Health**: `GET /api/health` returns `{"status":"ok", ...}`.
2. **Route triage (typed text)** — open the ClaimReady widget → "Let us approximate
   your route for you". Type a narrative such as:
   > I paid a $1,000 deposit to a furniture shop in January for a sofa that was
   > never delivered, and they will not refund me.
   Click **Get an approximate route**. Expect a real (non-mocked) suggestion
   screen naming something like *Contract for Sale of Goods* and SCT wording.
   Then **Continue to pre-filing form**.
3. **Auto-fill + tooltips** — on the form, fields the extractor is confident about
   (respondent/amount/statement) should already be filled. Click an `(i)` icon:
   expect a real "Suggested value" + source, or an honest "No suggestion yet"
   state — never a fabricated citation.
4. **Document upload via OCR** — on Page 1 (or via "Add more documents" after
   Save), attach a scanned PDF or image and run/continue. Expect the document to
   be processed (OCR on scan pages) and its text to drive suggestions.
5. **Tone advisory** — in the "Brief statement of claim" enter a hostile phrase
   such as *these young people are always useless and stole my money* plus the
   rest of the story (10+ chars). Fill every field, click **Submit** and expect:
   inline validation (if fields are wrong) → amber tone advisory with
   **Revise statement** / **Use the suggested wording** / **Continue anyway**.
6. **PDF + reference** — choose **Continue anyway** (or revise and resubmit).
   Expect an `SCT_PreFiling_Claim_*.pdf` download and the after-filing page
   showing the server-generated reference (not `CLAIMREADY-DEMO-xxxx`).
7. **Offline/error state** — stop the server, then try route triage again: expect
   a clear "Cannot reach the assistant service…" message, not a spinner.

## curl smoke

```bash
# Text extraction
curl -s -X POST http://127.0.0.1:8743/api/extract-fields \
  -H 'Content-Type: application/json' \
  -d '{"text":"Jane owes John $1,200 for a sofa that was never delivered."}'

# Document ingestion (text-layer PDF) with extra typed text
curl -s -X POST http://127.0.0.1:8743/api/extract-document \
  -F 'files=@sample.pdf' -F 'text=the sofa was ordered in March'

# Validate
curl -s -X POST http://127.0.0.1:8743/api/validate-claim \
  -H 'Content-Type: application/json' -d @- <<'JSON'
{"claimant_name":"John Doe","claimant_nric":"S1234567A","claimant_email":"j@x.com",
 "respondent_name":"Jane Ong","respondent_address":"1 Test Street Singapore 123456",
 "nature_of_dispute":"Contract for Sale of Goods","claim_amount":"1200",
 "date_of_cause_of_action":"2026-03-01",
 "particulars":"Respondent did not deliver goods I paid for in full."}
JSON

# Generate PDF (check X-Reference-Number response header)
curl -s -D - -o prefiling.pdf -X POST http://127.0.0.1:8743/api/generate-pdf \
  -H 'Content-Type: application/json' \
  -d '{"claimant_name":"John Doe","claimant_nric":"S1234567A","claimant_email":"j@x.com",
       "respondent_name":"Jane Ong","respondent_address":"1 Test Street Singapore 123456",
       "nature_of_dispute":"Contract for Sale of Goods","claim_amount":"1200",
       "date_of_cause_of_action":"2026-03-01",
       "particulars":"Respondent did not deliver goods I paid for in full."}'
```
