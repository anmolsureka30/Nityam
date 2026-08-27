# SMRITI Observatory

A real-time companion to Google ADK web: watches every SMRITI memory-layer
read/write (workflow / episodic / long-term tiers) as a tutor agent session
runs, correlated to the live OpenTelemetry trace span that caused it.

See `docs/superpowers/specs/2026-08-27-smriti-observatory-design.md` for the
full design, and `docs/superpowers/plans/2026-08-27-smriti-observatory.md`
for how it was built.

## Running locally

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

## Gotchas hit getting this running

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
