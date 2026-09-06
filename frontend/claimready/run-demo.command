#!/bin/bash
# Double-click launcher: starts the full ClaimReady demo. The FastAPI app
# (repo root app.py) serves both the /api endpoints and the frontend folder,
# so the widget's "approximate my route" / document upload flows work.
set -e
cd "$(dirname "$0")/.."

PORT=8743
URL="http://localhost:$PORT/dummy-website.html"

command -v uv >/dev/null 2>&1 || { echo "uv is required but was not found on PATH." >&2; exit 1; }

echo "Starting the ClaimReady demo (FastAPI on port $PORT)..."
echo "Repo root: $(pwd)"
echo "URL:       $URL"
echo
echo "Press Ctrl+C in this window to stop the server when you're done."
echo

if [ ! -f .env ]; then
  echo "Warning: no .env file found. Copy .env.example to .env and add an"
  echo "API key before live extraction/PDF generation will work."
  echo
fi

# Open the browser shortly after the server comes up.
( sleep 4; open "$URL" ) >/dev/null 2>&1 || true

uv run python app.py
