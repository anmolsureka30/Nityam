# Nityam

A personalized AI tutor. Structure:

- **`sub_modules/shruti/`** — the video-lecture-to-knowledge-graph extraction pipeline. A self-contained project (own `pyproject.toml`, `uv.lock`, tests, docs). See `sub_modules/shruti/docs/` for its architecture, implementation plans, and design docs.
- **`project_documentation/`** — Nityam-level architecture and research, not specific to any one submodule:
  - `memory_nityam_architecture/` — the memory-layer/SMRITI architecture wiki (start at its `README.md`).
  - `wiki/` — Google platform/ADK research that fed the platform decisions (start at `wiki/index.md`).

## Running Shruti

```bash
cd sub_modules/shruti
uv sync
cp .env.example .env  # fill in your own credentials
uv run --env-file .env python -m shruti.cli ingest
```

See `sub_modules/shruti/docs/architecture.md` and `sub_modules/shruti/justfile` for more commands.
