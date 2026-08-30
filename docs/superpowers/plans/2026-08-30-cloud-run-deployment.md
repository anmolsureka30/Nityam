# Cloud Run Deployment Implementation Plan

**Goal:** Deploy the entire Nityam app (FastAPI backend, all 5 ADK agents, the built frontend) as
one Cloud Run Service, plus Shruti's ingest pipeline as a separate Cloud Run Job, wired together by
an authenticated sync webhook.

**Spec:** `docs/superpowers/specs/2026-08-30-cloud-run-deployment-design.md` (extends the earlier
`deployment.md` research doc, both at repo root/docs).

## Global Constraints

- Region: `us-central1` for every resource (Cloud Run Service, Cloud Run Job, Memorystore, Cloud
  SQL, Artifact Registry).
- `--min-instances=1` on the main service; manual deploy only, no CI/CD this pass.
- Local dev (`./run.sh`) must keep working unmodified — the Shruti-trigger code path branches on an
  env var (`NITYAM_SHRUTI_MODE`, default `subprocess`) rather than assuming Cloud Run everywhere.
- No secret values ever get printed, echoed, or committed.

## Task 1 — `parse_wiki_text`: a markdown-string entry point alongside the existing file-based one

The Job won't share a filesystem with the backend service, so the sync webhook needs to accept wiki
markdown as text in the request body, not a path to read.

**File:** `backend/app/memory/shruti_sync.py`

Add, next to the existing `parse_wiki_file`:
```python
def parse_wiki_text(text: str, slug: str, subject: str = "projectile") -> list[GroundingChunk]:
    """Same parsing as parse_wiki_file, for content that arrives as a string
    (the sync webhook's request body) rather than a local path — the shape
    once Shruti runs somewhere that doesn't share a filesystem with this
    process."""
    concept_id = f"{subject}.{slug}" if subject else slug
    chunks = []
    for match in _SECTION.finditer(text):
        location = match.group("location")
        chunks.append(GroundingChunk(
            chunk_id=f"{slug}_{location.replace(':', '')}",
            source_type="lecture",
            source_ref=match.group("source_ref"),
            location=location,
            concept_ids=[concept_id],
            text=match.group("body").strip(),
        ))
    return chunks
```
Refactor `parse_wiki_file` to call it (`return parse_wiki_text(path.read_text(), path.stem, subject)`)
so the section-parsing logic exists exactly once.

Add a matching entry point to `sync_ingested_recording` for text-based input: rename the current
function's body into a private `_sync(chunks_by_slug: dict[str, list[GroundingChunk]], ...)` core,
and add two thin public wrappers — `sync_ingested_recording` (unchanged signature, reads from
`wiki_dir`, used by local/subprocess mode) and `sync_ingested_recording_from_text` (takes
`{slug: markdown_text}` instead of `wiki_dir`, used by the webhook). Both end by calling the shared
core so `put_current_topic`/`add_topic_history` logic exists once.

## Task 2 — `POST /admin/sync-grounding`, authenticated Job→Service webhook

**File:** `backend/app/admin_routes.py` (new)

```python
"""Endpoints called by other Google Cloud resources, not by browsers.

Today: the Shruti Cloud Run Job, reporting back what it extracted. Not
under app/memory_routes.py's `/memory` prefix because these aren't reads a
student's browser ever makes — a different trust boundary (service-to-
service ID tokens, not Firebase user tokens) deserves a different module,
not just a different route.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from app.memory import shruti_sync, store

log = logging.getLogger("nityam.admin_routes")

router = APIRouter(prefix="/admin")

_request_adapter = google_requests.Request()


def _expected_caller() -> str:
    email = os.environ.get("NITYAM_SHRUTI_JOB_SA", "").strip()
    if not email:
        raise HTTPException(status_code=503, detail="NITYAM_SHRUTI_JOB_SA is not configured")
    return email


def _verify_job_caller(authorization: str) -> None:
    """Confirms the caller genuinely is the Shruti Job's own service account
    — a Cloud Run ID token, not a Firebase user token (app/user_auth.py's
    concern is a different one: browsers, not other Google Cloud resources).
    The main service stays 'allow unauthenticated' for real student traffic
    (the WebSocket, the static frontend), so this check happens here, at the
    application layer, not via Cloud Run's own platform-level IAM."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:].strip()
    audience = os.environ.get("NITYAM_BACKEND_SERVICE_URL", "").strip()
    if not audience:
        raise HTTPException(status_code=503, detail="NITYAM_BACKEND_SERVICE_URL is not configured")
    try:
        claims = google_id_token.verify_oauth2_token(token, _request_adapter, audience=audience)
    except Exception as exc:  # noqa: BLE001 - any verification failure is a 401, not a 500
        log.warning("sync-grounding: token rejected: %s: %s", exc.__class__.__name__, exc)
        raise HTTPException(status_code=401, detail="invalid token") from None
    if claims.get("email") != _expected_caller():
        log.warning("sync-grounding: unexpected caller %r", claims.get("email"))
        raise HTTPException(status_code=403, detail="caller is not the Shruti job")


class ConceptPage(BaseModel):
    slug: str
    wiki_markdown: str


class SyncGroundingRequest(BaseModel):
    student_id: str
    recording_slug: str
    subject: str = "projectile"
    video_title: str = ""
    youtube_url: str = ""
    concepts: list[ConceptPage]


@router.post("/sync-grounding")
async def sync_grounding_endpoint(
    req: SyncGroundingRequest, authorization: str = Header(default=""),
):
    _verify_job_caller(authorization)
    written = shruti_sync.sync_ingested_recording_from_text(
        {c.slug: c.wiki_markdown for c in req.concepts},
        recording_slug=req.recording_slug,
        student_id=req.student_id,
        subject=req.subject,
        video_title=req.video_title,
        youtube_url=req.youtube_url,
    )
    return {"written": written}
```

Wire it in `backend/app/main.py`: `from app.admin_routes import router as admin_router` and
`app.include_router(admin_router)` next to the existing two `include_router` calls.

Add `google-auth` to `backend/requirements.txt` if not already present as a transitive dependency
(check first — `google-cloud-firestore`/`firebase-admin` likely already pull it in; add explicitly
only if `pip show google-auth` comes back empty in the venv).

## Task 3 — Shruti-trigger mode switch in `shruti_routes.py`

**File:** `backend/app/shruti_routes.py`

Add a module-level `_MODE = os.environ.get("NITYAM_SHRUTI_MODE", "subprocess").strip().lower()`.
`start_ingest` and `_run_worker` branch on `_MODE`:

- `"subprocess"` (default — local dev, `./run.sh`, unchanged): exactly today's code.
- `"cloud_run_job"` (production): `start_ingest` calls a new `_trigger_job(req, run_id, video_title)`
  that uses `google.cloud.run_v2.JobsClient().run_job(...)` with the ingest parameters passed as
  container env overrides (`RunJobRequest(name=JOB_NAME, overrides=...)` — the Job name comes from
  `NITYAM_SHRUTI_JOB_NAME` env var, format
  `projects/{project}/locations/us-central1/jobs/nityam-shruti-job`). Returns the Execution's
  resource name as `run_id` instead of a locally-minted UUID. `get_run` branches the same way:
  `"cloud_run_job"` mode calls `JobsClient.get_execution(name=run_id)` and maps its
  `succeeded_count`/`failed_count`/`running_count` fields to the existing `RunStatus` values instead
  of reading `_runs`/a log file. `video_title` (resolved via oEmbed, unchanged either way) needs
  its own small in-process cache keyed by `run_id` since Job Executions don't carry it — reuse the
  existing `_runs` dict for exactly that one field in both modes, nothing else.

Add `google-cloud-run` to `backend/requirements.txt`.

## Task 4 — Shruti Job entrypoint

**File:** `sub_modules_examples/shruti/shruti/job_entrypoint.py` (new)

Reads ingest parameters from env vars (`SHRUTI_YOUTUBE_URL`, `SHRUTI_STUDENT_ID`,
`SHRUTI_SUBJECT`, `SHRUTI_GRADE`, `SHRUTI_CHAPTER`, `SHRUTI_VIDEO_TITLE`) — this is the Job's actual
container entrypoint (`CMD` in its Dockerfile), replacing the interactive `shruti ingest` CLI
invocation for this path (the CLI itself is untouched — still works for a person at a terminal).

```python
"""Cloud Run Job entrypoint: run a Shruti ingest, then report the result to
Nityam's backend over the authenticated sync webhook — see
docs/superpowers/specs/2026-08-30-cloud-run-deployment-design.md §4. Only
used when NITYAM_SHRUTI_MODE=cloud_run_job; the interactive `shruti ingest`
CLI command is unaffected and still works exactly as before."""
import asyncio
import os
import sys

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token


def _env(name: str, required: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if required and not value:
        print(f"missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    youtube_url = _env("SHRUTI_YOUTUBE_URL")
    student_id = _env("SHRUTI_STUDENT_ID")
    subject = os.environ.get("SHRUTI_SUBJECT", "").strip() or "projectile"
    grade = os.environ.get("SHRUTI_GRADE", "").strip()
    chapter = os.environ.get("SHRUTI_CHAPTER", "").strip()
    video_title = os.environ.get("SHRUTI_VIDEO_TITLE", "").strip()
    backend_url = _env("NITYAM_BACKEND_SERVICE_URL")

    from shruti.cli import _download_youtube  # reuse, not reimplement
    from google import genai

    print(f"Downloading {youtube_url} ...")
    video_path = _download_youtube(youtube_url)

    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()

    from shruti.ingest import run_ingest
    summary = asyncio.run(run_ingest(
        video_path, client,
        subject=subject or None, grade=int(grade) if grade else None, chapter=chapter or None,
    ))

    from pathlib import Path
    wiki_dir = Path("vault/wiki")
    concepts = []
    for slug in summary.get("concept_ids", []):
        path = wiki_dir / f"{slug}.md"
        if path.exists():
            concepts.append({"slug": slug, "wiki_markdown": path.read_text()})

    if not concepts:
        print("no concepts produced — nothing to sync")
        return

    token = google_id_token.fetch_id_token(GoogleRequest(), backend_url)
    resp = requests.post(
        f"{backend_url}/admin/sync-grounding",
        json={
            "student_id": student_id,
            "recording_slug": summary["recording_slug"],
            "subject": subject,
            "video_title": video_title,
            "youtube_url": youtube_url,
            "concepts": concepts,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"synced {len(concepts)} concept(s): {resp.json()}")


if __name__ == "__main__":
    main()
```

Add `requests` to Shruti's `pyproject.toml` dependencies if not already present (check first).

## Task 5 — Two Dockerfiles

**File:** `backend/Dockerfile` (new) — multi-stage, per the spec's §3:
```dockerfile
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN adduser --disabled-password --gecos "" myuser
COPY backend/ .
COPY --from=frontend /fe/dist /app/frontend/dist
RUN chown -R myuser:myuser /app
USER myuser
ENV PATH="/home/myuser/.local/bin:$PATH"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
```
(Build context must be the **repo root**, not `backend/`, so the frontend stage can `COPY frontend/`
— `docker build -f backend/Dockerfile .` from the repo root.)

**File:** `sub_modules_examples/shruti/Dockerfile` (new):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y
ENV PATH="/root/.deno/bin:$PATH"
RUN pip install --no-cache-dir uv
COPY sub_modules_examples/shruti/pyproject.toml sub_modules_examples/shruti/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY sub_modules_examples/shruti/ .
RUN uv sync --frozen
RUN uv tool install yt-dlp
ENV PATH="/root/.local/bin:$PATH"
CMD ["uv", "run", "python", "-m", "shruti.job_entrypoint"]
```
(Build context is also the repo root, same reasoning, path prefix instead — confirm during
execution whether Shruti's `pyproject.toml` needs any path adjustment for this build context; if
so, that's a real, small fix to make then, not a design change.)

Add a root `.dockerignore` (node_modules, .venv, __pycache__, .git, .local/, logs/).

## Task 6 — GCP provisioning (no code, direct `gcloud`/`docker` execution)

Run in order, verifying each before the next:
1. Enable APIs: `redis.googleapis.com`, `secretmanager.googleapis.com`, `sqladmin.googleapis.com`,
   `run.googleapis.com` (idempotent — already on).
2. Create `nityam-backend-sa` and `nityam-shruti-job-sa`; grant roles per spec §5.
3. Create the Artifact Registry repo (`nityam` in `us-central1`).
4. Create the Memorystore instance (spec/`deployment.md` §5 command) — **real ongoing cost, confirm
   before creating**.
5. Create the Cloud SQL Postgres instance for Shruti, smallest tier, `pgvector` extension enabled —
   **real ongoing cost, confirm before creating**.
6. Build + push both images.
7. Deploy the Cloud Run Job (`nityam-shruti-job`) — needs `NITYAM_BACKEND_SERVICE_URL` set, which
   isn't known until step 8 creates the Service; deploy the Job with a placeholder then `gcloud run
   jobs update` once the Service URL exists (or deploy Service first with a temporary
   `NITYAM_SHRUTI_JOB_NAME` placeholder and update after the Job exists — either ordering works,
   pick one during execution and update the other after both exist).
8. Deploy the Cloud Run Service with every flag from `deployment.md` §4 + this spec.
9. Verify: `/health`, a real WebSocket session, a real Shruti upload through to
   `/admin/sync-grounding` landing in Firestore.

## Self-review notes

- Task 3's mode switch is the one piece keeping local dev (`./run.sh`) working unmodified — verified
  the default (`subprocess`) preserves every existing local-dev code path byte-for-byte.
- Task 2's auth check is deliberately app-level, not Cloud Run IAM, because the Service must stay
  publicly reachable for real student traffic — consistent with the spec.
- Circular env-var dependency between the Job and Service URLs (Task 6 step 7) is real and
  resolved by a two-pass deploy, not a design gap.
