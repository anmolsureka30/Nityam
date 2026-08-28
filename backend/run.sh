#!/usr/bin/env bash
# Starts the Nityam backend, and the Vite dev server unless told otherwise.
#   ./run.sh            backend + frontend dev server (hot reload)
#   ./run.sh --api-only  backend only
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python

# A virtualenv bakes its absolute path into every console script, so renaming
# or moving this folder silently breaks `.venv/bin/uvicorn` while
# `.venv/bin/python` still looks fine. Test that it actually runs, not that it
# exists.
if [[ -x "$PY" ]] && ! .venv/bin/uvicorn --version >/dev/null 2>&1; then
  echo "The virtualenv points at an old path (this folder was moved). Rebuilding…"
  rm -rf .venv
fi

if [[ ! -x "$PY" ]]; then
  echo "No virtualenv. Creating one (needs Python 3.10+)…"
  PYBIN="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)"
  [[ -n "$PYBIN" ]] || { echo "Install Python 3.10+ first: brew install python@3.12"; exit 1; }
  "$PYBIN" -m venv .venv
  $PY -m pip install --quiet --upgrade pip
  $PY -m pip install --quiet -r requirements.txt
fi

if grep -qE '^NITYAM_AUTH=mock' .env 2>/dev/null; then
  echo "── mock mode: no credentials needed ────────"
  echo "   (set NITYAM_AUTH in .env to talk to real Gemini)"
else
  echo "── credentials ─────────────────────────────"
  $PY -m app.auth || echo "(continuing anyway — set NITYAM_AUTH=mock to run without credentials)"
fi
echo

# Seed the demo student on first run, or every memory tool returns found:false
# and the tutor has nothing to teach from.
if [[ ! -f data/memory.db ]]; then
  echo "No memory store yet — seeding the demo student…"
  $PY -m scripts.seed_demo_data
  echo
  $PY -m scripts.create_demo_firebase_user || {
    echo "(no demo Firebase user — nobody can sign in as demo_student yet."
    echo " Fix: gcloud auth application-default login"
    echo "      .venv/bin/python -m scripts.create_demo_firebase_user)"
  }
  echo
fi

# A busy port used to fail silently: uvicorn exited, Vite started anyway, and
# the page loaded with a mic that could never connect. Say so and stop.
PORT="${NITYAM_API_PORT:-8210}"
WEB_PORT="${NITYAM_WEB_PORT:-5173}"
busy() {
  local port="$1" what="$2" var="$3" alt="$4"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return 0
  echo "Port $port ($what) is already in use, so stopping here."
  echo
  echo "  What is holding it:"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN | sed "s/^/    /"
  echo
  echo "  If it is a leftover from an earlier run:"
  echo "    kill \$(lsof -t -iTCP:$port -sTCP:LISTEN)"
  echo "  If it is something else you need, move ours instead:"
  echo "    $var=$alt ./run.sh"
  exit 1
}

# Both ports are checked, not just the API one. A busy API port used to fail
# silently — uvicorn exited, Vite started anyway, and the page loaded with a mic
# that could never connect. A busy web port is the same class of problem from
# the other end, and strictPort means Vite refuses rather than drifting to
# another port, which is the right call but needs saying clearly.
busy "$PORT" "backend API" NITYAM_API_PORT "$((PORT + 1))"
[[ "${1:-}" == "--api-only" ]] || busy "$WEB_PORT" "frontend dev server" NITYAM_WEB_PORT "$((WEB_PORT + 1))"

# `kill 0` signals the whole process group, which is right when this script is
# a group leader (an interactive shell gives it one) and a no-op or worse when
# it is not — running it as `(./run.sh &)` left a Vite dev server holding port
# 5173 after the parent was gone.
#
# There is no setsid on macOS, so children cannot be put in their own groups to
# be killed wholesale. Both children also fork: uvicorn --reload runs a reloader
# that spawns the real server, and npm runs vite. So: signal the children, then
# their children, and finally take out anything still LISTENING on our two
# ports. That last step is what actually guarantees the next ./run.sh starts —
# it targets the observed symptom rather than trying to model a process tree.
CHILDREN=()

port_holder() { lsof -t -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null; }

cleanup() {
  trap - EXIT INT TERM
  for pid in "${CHILDREN[@]}"; do
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  for _ in 1 2 3 4 5 6; do
    [[ -n "$(port_holder "$PORT")$(port_holder "$WEB_PORT")" ]] || break
    sleep 0.5
  done
  for port in "$PORT" "$WEB_PORT"; do
    for pid in $(port_holder "$port"); do
      kill -KILL "$pid" 2>/dev/null || true
    done
  done
}
trap cleanup EXIT INT TERM

spawn() {
  "$@" &
  CHILDREN+=("$!")
}

spawn .venv/bin/uvicorn app.main:app --port "$PORT" --reload --reload-dir app

if [[ "${1:-}" == "--api-only" ]]; then
  echo "Backend on http://localhost:$PORT"
else
  FE=../frontend
  [[ -d "$FE/node_modules" ]] || (cd "$FE" && npm install)
  spawn env -C "$FE" NITYAM_WEB_PORT="$WEB_PORT" NITYAM_API_PORT="$PORT" npm run dev
  echo "Open http://localhost:$WEB_PORT"
fi

wait
