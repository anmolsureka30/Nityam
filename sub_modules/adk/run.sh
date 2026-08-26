#!/usr/bin/env bash
# Starts the backend, and the Vite dev server unless the app is already built.
#   ./run.sh          backend + vite dev  (hot reload)
#   ./run.sh --built  backend only, serving frontend/dist
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "No virtualenv. Creating one (needs Python 3.10+)…"
  PYBIN="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)"
  [[ -n "$PYBIN" ]] || { echo "Install Python 3.10+ first: brew install python@3.12"; exit 1; }
  "$PYBIN" -m venv .venv
  $PY -m pip install --quiet --upgrade pip
  $PY -m pip install --quiet -r backend/requirements.txt
fi

if grep -qE '^NITYAM_AUTH=mock' .env 2>/dev/null; then
  echo "── mock mode: no credentials needed ────────"
  echo "   (set NITYAM_AUTH in .env to talk to real Gemini)"
else
  echo "── credentials ─────────────────────────────"
  $PY backend/auth.py || echo "(continuing anyway — set NITYAM_AUTH=mock to run without credentials)"
fi
echo

# A busy port used to fail silently: uvicorn exited, Vite started anyway, and
# the page loaded with an orb that could never connect. Say so and stop.
PORT=8000
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use — probably a backend left over from an"
  echo "earlier run. The page would load but never connect, so stopping here."
  echo
  echo "  What is holding it:"
  lsof -nP -iTCP:$PORT -sTCP:LISTEN | sed "s/^/    /"
  echo
  echo "  To free it:  kill \$(lsof -t -iTCP:$PORT -sTCP:LISTEN)"
  exit 1
fi

trap 'kill 0' EXIT

.venv/bin/uvicorn --app-dir backend main:app --port $PORT --reload &

if [[ "${1:-}" == "--built" ]]; then
  echo "Backend on http://localhost:$PORT (serving frontend/dist)"
else
  [[ -d frontend/node_modules ]] || (cd frontend && npm install)
  (cd frontend && npm run dev) &
  echo "Open http://localhost:5173"
fi

wait
