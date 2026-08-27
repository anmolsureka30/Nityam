# SMRITI Observatory

Real-time visualization of every SMRITI memory-layer read/write (workflow / episodic /
long-term tiers) as a tutor agent session runs, correlated to the live OpenTelemetry trace that
caused it.

Two ways to see it — pick one:

## Option A: `adk-web/` — memory built into ADK web itself (recommended)

A maintained fork of [google/adk-web](https://github.com/google/adk-web) with the memory layer
wired directly in: a **Memory** tab in the side panel (next to State/Artifacts/Evals) showing
Working/Episodic/Long-Term memory for the session's student, live, plus a "Memory operations from
this trace" section inside the trace inspector. No second server — it reads
`/memory/sessions/{id}/state` and `/events`, two endpoints added directly to the tutor app's own
FastAPI server (`sub_modules_examples/tutor/app/app_utils/memory_routes.py`).

```bash
# 1. The tutor app (separate terminal, from sub_modules_examples/tutor/)
ALLOW_ORIGINS=http://localhost:4200 uv run uvicorn app.fast_api_app:app --port 8010

# 2. adk-web, pointed at it
cd adk-web
npm install                                       # first time only
npm run serve --backend=http://127.0.0.1:8010 -- --port 4200
```

Open `http://localhost:4200`. Design rationale:
`docs/superpowers/specs/2026-08-27-adk-web-memory-integration-design.md`.

**Known caveat:** ADK web's own span data represents large (128-bit) OpenTelemetry trace IDs as
JS numbers, which lose precision (renders as e.g. `1.5e+38`). This defeats the trace-tab memory
section's exact-match correlation specifically — the Memory tab is unaffected. Worth a fix
upstream in ADK web's own trace serialization.

## Option B: `backend/` + `frontend/` — standalone companion app

A separate React/FastAPI app that watches the same memory events over a WebSocket, styled as an
ADK-web-adjacent companion rather than living inside it. Predates Option A; kept for now as a
fallback since Option A is newer and less battle-tested end to end.

```bash
# 1. The tutor app (separate terminal, from sub_modules_examples/tutor/)
uv run uvicorn app.fast_api_app:app --port 8000

# 2. This backend
cd backend && uv run uvicorn observatory.main:app --reload --port 8100

# 3. This frontend
cd frontend && npm run dev
```

Requires local Redis (`brew services start redis`) and `gcloud auth
application-default login` against the `nityam-506707` project — see
`backend/.env.example`.

### Gotchas hit getting this running

- **Backend won't import `app`:** uv's editable install of the `tutor`
  package writes a `.pth` file that isn't always picked up by `uv run`.
  If `observatory.main` fails with `ModuleNotFoundError: No module named
  'app'`, launch with `PYTHONPATH=<absolute path to sub_modules_examples/tutor>`
  set explicitly:
  ```bash
  PYTHONPATH=/absolute/path/to/sub_modules_examples/tutor \
    .venv/bin/python -m uvicorn observatory.main:app --port 8100
  ```
- **Frontend shows an empty session list:** the backend's CORS config only
  allows `http://localhost:5173` — browsers treat `localhost` and
  `127.0.0.1` as different origins, so opening the frontend via
  `127.0.0.1:5173` silently fails every fetch. Always use `localhost`.
- **Port 8000 already taken:** if another process/session already has it,
  just run the tutor app on a different port and set `TUTOR_BASE_URL`
  accordingly for both the backend and the frontend's `VITE_TUTOR_BASE_URL`.

See `docs/superpowers/specs/2026-08-27-smriti-observatory-design.md` for the
full design, and `docs/superpowers/plans/2026-08-27-smriti-observatory.md`
for how it was built.
