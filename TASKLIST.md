# ClaimReady run task list

## Current status

- Database: **not configured**. The app currently keeps uploaded files and form state in memory for the browser session; there are no database models, migrations, connection settings, or persistence endpoints.

## One-time setup

- [ ] Use Python 3.11+ and create/activate the repository virtual environment.
- [ ] Install dependencies from `pyproject.toml` (or sync with `uv.lock`).
- [ ] Copy `.env.example` to `.env`.
- [ ] Set the configured chat/embedding provider and API key in `.env`.
- [ ] Confirm OCR dependencies are available if scanned PDFs or images will be used.

## Start and verify locally

- [ ] Start the API from the repository root: `python app.py`.
- [ ] Open `http://127.0.0.1:8743/` in a browser.
- [ ] Check `GET /api/health` returns `status: ok`.
- [ ] Submit typed claim text and confirm field suggestions appear.
- [ ] Upload a text PDF and confirm its filename appears as the suggestion source.
- [ ] Upload a scanned image/PDF and confirm OCR succeeds (or the UI reports that OCR is unavailable).
- [ ] Delete an attached file and confirm it disappears and is excluded from the next analysis.
- [ ] Review every suggestion before using it in the form.

## Quality gate before sharing

- [ ] Run `.\\.venv\\Scripts\\python.exe -m pytest -q`.
- [ ] Check the browser console and API logs for errors.
- [ ] Keep real personal data and production credentials out of demo environments.
- [ ] Configure allowed `CORS_ORIGINS` if serving the frontend from another origin.
- [ ] Put authentication, storage, retention, monitoring, and production OCR/provider configuration in place before deployment.
