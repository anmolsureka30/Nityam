# Nityam

A personalized AI tutor — Gemini Live voice, a shared board the tutor writes on, and SMRITI, a
three-tier memory layer (workflow / episodic / long-term) that every claim in a student's memory
cites evidence back to.

## Structure

- **`backend/`** + **`frontend/`** — the real production tutor: a Gemini Live voice loop, a
  routing voice agent over four reasoning specialists (`VoiceAgent` → `BoardAgent` /
  `ArtifactAgent` / `QuizAgent` / `TextbookAgent`), and a shared canvas the tutor writes on and
  the student points at. Custom-built (not the ADK dev-server scaffold below) — see
  `backend/README.md` to run it.
- **`sub_modules_examples/tutor/`** — an ADK (Google Agent Development Kit)-scaffolded reference
  implementation of the same memory layer and agent topology, used for ADK-tooling-specific work
  (evals, the ADK dev-ui, the SMRITI Observatory below). Runs side by side with `backend/` on
  different ports (`8010`/`4200` here vs `8210`/`5173` there) — see its own `AGENTS.md`/`CLAUDE.md`.
  **`backend/app/memory/`** is a manually-synced copy of `sub_modules_examples/tutor/app/memory/`
  (see `backend/app/memory/store.py`'s own header comment) — a fix landed in one needs porting to
  the other by hand; there's no automated sync. Check both when touching memory-layer code.
- **`smriti-observatory/`** — real-time visualization of SMRITI memory state as a tutor session
  runs, built against the ADK reference implementation. See `smriti-observatory/README.md` for the
  two ways to run it (a maintained fork of ADK web with memory built in, or a standalone
  React/FastAPI companion app).
- **`sub_modules/shruti/`** — the video-lecture-to-knowledge-graph extraction pipeline that makes
  citation possible. A self-contained project (own `pyproject.toml`, `uv.lock`, tests, docs). See
  `sub_modules/shruti/docs/` for its architecture, implementation plans, and design docs.
- **`sub_modules_examples/artifact_generator/`** — generates the interactive physics
  visualizations (`ArtifactAgent`'s output) both `backend/` and `sub_modules_examples/tutor/`
  render.
- **`project_documentation/`** — Nityam-level architecture and research, not specific to any one
  submodule:
  - `memory_nityam_architecture/` — the memory-layer/SMRITI architecture wiki (start at its
    `README.md`) — the design, the Firestore/Redis/GCS migration, and the real multi-persona eval
    results.
  - `wiki/` — Google platform/ADK research that fed the platform decisions (start at
    `wiki/index.md`).

## Running the tutor

```bash
cd backend
cp .env.example .env        # then fill in credentials, or set NITYAM_AUTH=mock
./run.sh                    # backend + frontend dev server
```

See `backend/README.md` for the full picture — the agent topology, mock mode, and the
`scripts/drive.py` smoke test ("the one to reach for when the tutor stops writing on the board").

## Running Shruti

```bash
cd sub_modules/shruti
uv sync
cp .env.example .env  # fill in your own credentials
uv run --env-file .env python -m shruti.cli ingest
```

See `sub_modules/shruti/docs/architecture.md` and `sub_modules/shruti/justfile` for more commands.

## Memory-layer evals

`sub_modules_examples/tutor/tests/eval/memory_eval/` runs the real `TutorAgent` through five
multi-session student personas against real Firestore/Redis, with deterministic checks (D1-D7) and
LLM-as-judge checks (L1-L4) — see `project_documentation/memory_nityam_architecture/README.md` for
the reading order and `memory_layer_eval_report.md` for the latest results.

```bash
cd sub_modules_examples/tutor
uv run python -m tests.eval.memory_eval.run_eval
```
