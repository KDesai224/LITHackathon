# Service-oriented layout

The demo is organized around independently testable service boundaries:

```text
.
├── app.py                 # API gateway and local composition root
├── backend/               # API support services (tone, evidence, PDF)
├── sct_intake/            # intake and field extraction domain service
├── ocr_engine/            # document text ingestion service
├── frontend/claimready/   # static browser client and its assets
├── scripts/               # manual/demo utilities
└── tests/                 # cross-service and unit tests
```

`app.py` composes the services for a single-process local demo. The package
boundaries are intentionally independent: `sct_intake` owns structured case
data and extraction, `ocr_engine` owns PDF/image text extraction, and
`backend` owns API-facing validation and document generation. This keeps the
same code easy to split into separately deployed processes later without
coupling the frontend to internal modules.

The browser client is served by the API at `/dummy-website.html`; its source
files are all under `frontend/claimready/`.
