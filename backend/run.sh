#!/usr/bin/env bash
# Starts the Nityam backend, its frontend, and the Observatory (the live
# memory-visualization pair in ../smriti-observatory) — one command, four
# processes.
#   ./run.sh                  everything: backend + frontend + Observatory
#   ./run.sh --no-observatory backend + frontend only, no Observatory
#   ./run.sh --api-only       backend only, nothing browser-facing
set -euo pipefail
cd "$(dirname "$0")"

API_ONLY=0
NO_OBSERVATORY=0
for arg in "$@"; do
  case "$arg" in
    --api-only) API_ONLY=1 ;;
    --no-observatory) NO_OBSERVATORY=1 ;;
  esac
done
SKIP_OBSERVATORY=$(( API_ONLY || NO_OBSERVATORY ))

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
# The Observatory frontend's own vite.config.ts hardcodes port 5173 — a real
# collision with the line above. It's overridden with a CLI flag at spawn
# time below rather than edited in smriti-observatory's own source.
#
# The web port MUST be 3000: smriti-observatory/backend/observatory/main.py
# hardcodes its CORS allow_origins to exactly ["http://localhost:5173",
# "http://localhost:3000"] — nothing else is permitted, and a browser fetch
# from any other origin fails silently (no console-visible error beyond
# DevTools' network tab; the frontend's own .catch() just renders an empty
# session list). 5173 is already taken by the tutor's own frontend above, so
# 3000 is the only other origin the Observatory backend will actually answer.
OBS_PORT="${NITYAM_OBSERVATORY_PORT:-8100}"
OBS_WEB_PORT="${NITYAM_OBSERVATORY_WEB_PORT:-3000}"
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
[[ "$API_ONLY" == 1 ]] || busy "$WEB_PORT" "frontend dev server" NITYAM_WEB_PORT "$((WEB_PORT + 1))"
if [[ "$SKIP_OBSERVATORY" == 0 ]]; then
  busy "$OBS_PORT" "Observatory API" NITYAM_OBSERVATORY_PORT "$((OBS_PORT + 1))"
  busy "$OBS_WEB_PORT" "Observatory frontend" NITYAM_OBSERVATORY_WEB_PORT "$((OBS_WEB_PORT + 1))"

  echo "── Observatory prerequisites ───────────────"
  if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    echo "  [ ok ] Redis is reachable — Working-memory tier will show live data"
  else
    echo "  [warn] Redis not reachable — start it with: redis-server --daemonize yes"
    echo "         Without it, the Working-memory tier stays empty."
  fi
  if grep -qE '^NITYAM_STORE=firestore' .env 2>/dev/null; then
    echo "  [ ok ] NITYAM_STORE=firestore — Episodic/Long-term tiers will show live data"
  else
    echo "  [warn] NITYAM_STORE is not 'firestore' in .env — the Observatory reads"
    echo "         Firestore directly, so Episodic/Long-term will stay empty."
  fi
  echo
fi

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
    [[ -n "$(port_holder "$PORT")$(port_holder "$WEB_PORT")$(port_holder "$OBS_PORT")$(port_holder "$OBS_WEB_PORT")" ]] || break
    sleep 0.5
  done
  for port in "$PORT" "$WEB_PORT" "$OBS_PORT" "$OBS_WEB_PORT"; do
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

if [[ "$API_ONLY" == 1 ]]; then
  echo "Backend on http://localhost:$PORT"
else
  FE=../frontend
  [[ -d "$FE/node_modules" ]] || (cd "$FE" && npm install)
  spawn env -C "$FE" NITYAM_WEB_PORT="$WEB_PORT" NITYAM_API_PORT="$PORT" npm run dev
  echo "Open http://localhost:$WEB_PORT"
fi

if [[ "$SKIP_OBSERVATORY" == 0 ]]; then
  OBS_BE=../smriti-observatory/backend
  OBS_FE=../smriti-observatory/frontend
  # uv run syncs the venv from uv.lock on its own — no separate install step,
  # unlike the pip-based backend above. --reload-dir scopes the watcher to the
  # package itself, the same fix this repo's own reload storm needed: without
  # it, --reload also watches uv's cache writes under .venv and reloads on
  # every request.
  spawn env -C "$OBS_BE" \
    TUTOR_BASE_URL="http://localhost:$PORT" \
    GCP_PROJECT="${GCP_PROJECT:-nityam-506707}" \
    FIRESTORE_DATABASE="${FIRESTORE_DATABASE:-smriti}" \
    REDIS_HOST="${REDIS_HOST:-localhost}" \
    REDIS_PORT="${REDIS_PORT:-6379}" \
    uv run uvicorn observatory.main:app --port "$OBS_PORT" --reload --reload-dir observatory

  [[ -d "$OBS_FE/node_modules" ]] || (cd "$OBS_FE" && npm install)
  spawn env -C "$OBS_FE" \
    VITE_OBSERVATORY_BACKEND_URL="http://localhost:$OBS_PORT" \
    VITE_TUTOR_BASE_URL="http://localhost:$PORT" \
    VITE_GCP_PROJECT="${GCP_PROJECT:-nityam-506707}" \
    npm run dev -- --port "$OBS_WEB_PORT" --strictPort

  echo "Observatory on http://localhost:$OBS_WEB_PORT (auto-selects your session within ~4s of connecting)"
fi

wait
