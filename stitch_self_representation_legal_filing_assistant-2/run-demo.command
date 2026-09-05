#!/bin/bash
# Double-click launcher: serves the demo folder locally and opens the
# dummy website (with the ClaimReady overlay) in the default browser.
set -e
cd "$(dirname "$0")"

PORT=8743
URL="http://localhost:$PORT/dummy-website.html"

echo "Starting local server for the Legal Filing Assistant demo..."
echo "Folder: $(pwd)"
echo "URL:    $URL"
echo
echo "Press Ctrl+C in this window to stop the server when you're done."
echo

# Open the browser shortly after the server comes up.
( sleep 1; open "$URL" ) &

python3 -m http.server "$PORT"
