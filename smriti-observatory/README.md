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
