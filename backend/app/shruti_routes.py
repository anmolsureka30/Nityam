"""Thin, isolated wrapper around the Shruti video-ingest pipeline so the
dashboard's "paste a YouTube link" flow can trigger it and watch progress.

Shruti (sub_modules_examples/shruti/) is CLI-only today — confirmed no
FastAPI/HTTP surface exists anywhere in that package, only Typer CLI commands
(shruti/cli.py). Rather than importing its internals (a separate uv project,
its own venv, its own dependency set — including a Postgres/pgvector schema
this backend has no reason to know about), this module shells out to the
real CLI exactly as a person would from a terminal (`shruti ingest --url
...`) and tails its own stdout, which is the only progress signal the
pipeline produces (no streaming/event mechanism exists inside Shruti itself).

The only integration points are the two routes below, one `app.include_router(...)`
line in main.py, and — once a run finishes — app/memory/shruti_sync.py, which
mirrors the concepts this run touched into the same grounding_chunks/
current_topic store every tutoring session reads from (see that module's own
docstring; this is the live replacement for hand-running
scripts/seed_demo_data.py after every new recording).

State is a plain in-process dict: this backend is a single dev process
(uvicorn --reload notwithstanding — a code reload restarts the whole worker,
which is already true of every other transient state here, e.g. app/sessions.py's
in-memory session table). A run in progress does not survive a backend
restart; that is an acceptable limit for a best-effort dashboard feature, not
a silent bug — the frontend surfaces "unknown run" rather than hanging if it
polls a run_id that state doesn't remember.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.memory import shruti_sync

log = logging.getLogger("nityam.shruti_routes")

router = APIRouter(prefix="/shruti")

# backend/app/shruti_routes.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SHRUTI_DIR = REPO_ROOT / "sub_modules_examples" / "shruti"
WIKI_DIR = SHRUTI_DIR / "vault" / "wiki"
RUN_LOG_DIR = SHRUTI_DIR / ".local" / "dashboard_runs"

_RESULT_LINE = re.compile(r"^SHRUTI_RESULT_JSON: (.*)$", re.MULTILINE)

RunStatus = Literal["running", "done", "failed"]


class IngestRequest(BaseModel):
    youtube_url: str
    student_id: str
    """Whoever is uploading. current_topic is written per-student (see
    app/memory/shruti_sync.py) — without this, one person's upload would
    silently change what every other signed-in student's next session opens
    on, which is exactly the cross-student leak a shared-nothing memory
    layer exists to avoid."""
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None


class RunInfo(BaseModel):
    run_id: str
    status: RunStatus
    started_at: float
    returncode: int | None = None
    log_tail: str
    video_title: str = ""
    """Resolved best-effort via YouTube's oEmbed endpoint (no API key needed)
    the moment the link is submitted — before the 10-20 minute pipeline even
    starts, so the dashboard can show which video is being extracted rather
    than a bare URL. Empty if the lookup failed; never blocks the ingest."""


_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()

# How much of the log to hand back per poll — enough to read the last few
# stage transitions without the response growing unbounded on a long run.
_LOG_TAIL_CHARS = 6000


def _fetch_youtube_title(url: str) -> str:
    """YouTube's oEmbed endpoint, unauthenticated — the only reason this can
    run with no API key. Best-effort: any failure (offline, non-YouTube URL,
    a private/deleted video) just means an empty title, never a broken
    ingest — the pipeline itself doesn't need this at all."""
    try:
        oembed_url = "https://www.youtube.com/oembed?" + urlencode(
            {"format": "json", "url": url.strip()}
        )
        with urlopen(oembed_url, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("title", "")).strip()
    except Exception as e:
        log.info("could not resolve YouTube title for %s: %s", url, e)
        return ""


def _build_command(req: IngestRequest) -> list[str]:
    """No `--env-file .env` — that requires a physical
    sub_modules_examples/shruti/.env file to exist, which this repo never
    ships (it's gitignored, like every .env) and nobody creates by hand
    unless told to. `_subprocess_env()` below supplies the same credential
    directly instead, reusing whatever already authenticates THIS backend
    process — one less manual setup step, and one less way for a fresh
    clone to half-work."""
    cmd = ["uv", "run", "shruti", "ingest", "--url", req.youtube_url]
    if req.subject:
        cmd += ["--subject", req.subject]
    if req.grade is not None:
        cmd += ["--grade", str(req.grade)]
    if req.chapter:
        cmd += ["--chapter", req.chapter]
    return cmd


def _subprocess_env() -> dict[str, str]:
    """The environment `shruti ingest` actually runs with — this backend's
    own environment, plus one addition for exactly one auth mode.

    Shruti's own credential check (shruti/cli.py's `ingest`) only lights up
    on GOOGLE_OAUTH_ACCESS_TOKEN or GOOGLE_API_KEY, and only the former
    takes Shruti's `vertexai=True` client path — the one this project's key
    actually authenticates against (confirmed: a plain `genai.Client(api_key=
    ...)` call with this exact key returns 403 PERMISSION_DENIED; app/auth.py's
    own working vertex_express path is `genai.Client(vertexai=True, api_key=
    ...)`). When this backend is running in that mode, app/auth.configure()
    has already resolved the working key into GOOGLE_API_KEY in THIS
    process's environment — so it's copied under the name Shruti's own code
    already knows to trust the right way, rather than teaching Shruti a third
    branch. Left untouched for ai_studio (Shruti's own GOOGLE_API_KEY branch
    is already the correct one there) and for vertex/ADC (no key to copy —
    a real, separate gap in Shruti's own credential handling, not this one).

    Also sets PYTHONPATH to SHRUTI_DIR. Confirmed live, repeatedly: Shruti's
    installed console-script (`uv run shruti ...`) intermittently fails with
    `ModuleNotFoundError: No module named 'shruti'` even though the same
    command succeeds moments later with no change in between — its editable
    install's site-packages `.pth` linkage is flaky (reproduced with `uv
    run` bypassed entirely, so it isn't specific to how this file invokes
    it), and `uv sync --reinstall-package shruti` only fixes it until the
    next time it flakes. Setting PYTHONPATH is not a workaround for a
    one-off: it makes `import shruti` resolve via an explicit, always-
    correct path instead of the flaky editable-install machinery, so this
    integration doesn't depend on that machinery staying healthy at all."""
    env = dict(os.environ)
    if (
        os.environ.get("NITYAM_AUTH", "").strip().lower() == "vertex_express"
        and not env.get("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
    ):
        key = env.get("GOOGLE_API_KEY", "").strip()
        if key:
            env["GOOGLE_OAUTH_ACCESS_TOKEN"] = key
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SHRUTI_DIR}{os.pathsep}{existing}" if existing else str(SHRUTI_DIR)
    return env


def _sync_after_ingest(
    log_path: Path, student_id: str, subject: str, video_title: str, youtube_url: str,
) -> None:
    """Reads this run's own log for the CLI's `SHRUTI_RESULT_JSON:` marker
    line (see sub_modules_examples/shruti/shruti/cli.py) and mirrors the
    concepts it just wrote into Nityam's own grounding_chunks + current_topic
    — the live equivalent of hand-running scripts/seed_demo_data.py.

    Best-effort and separate from ingest success: the pipeline already ran
    and its vault/wiki pages already exist on disk regardless of what
    happens here, so a sync failure is logged, never raised into the worker
    thread (matches the spec's own §9 error-handling rule for this step)."""
    text = log_path.read_text(errors="replace")
    match = _RESULT_LINE.search(text)
    if not match:
        log.warning("shruti_sync: no SHRUTI_RESULT_JSON line found in %s", log_path)
        return
    try:
        summary = json.loads(match.group(1))
        shruti_sync.sync_ingested_recording(
            WIKI_DIR,
            recording_slug=summary["recording_slug"],
            concept_ids=summary.get("concept_ids", []),
            student_id=student_id,
            subject=subject,
            video_title=video_title,
            youtube_url=youtube_url,
        )
    except Exception:
        log.exception("shruti_sync: failed to sync run result from %s", log_path)


def _run_worker(
    run_id: str, cmd: list[str], log_path: Path,
    student_id: str, subject: str, video_title: str, youtube_url: str,
) -> None:
    try:
        with log_path.open("w") as log_file:
            log_file.write(f"$ {' '.join(cmd)}\n\n")
            log_file.flush()
            proc = subprocess.Popen(
                cmd, cwd=str(SHRUTI_DIR), stdout=log_file, stderr=subprocess.STDOUT,
                env=_subprocess_env(),
            )
            returncode = proc.wait()
    except OSError as e:
        # e.g. `uv` not on PATH in this process's environment — a real,
        # reportable failure, not a crash of the polling endpoint.
        with log_path.open("a") as log_file:
            log_file.write(f"\nFailed to start: {e}\n")
        returncode = -1

    if returncode == 0:
        _sync_after_ingest(log_path, student_id, subject or "projectile", video_title, youtube_url)

    with _runs_lock:
        state = _runs.get(run_id)
        if state is not None:
            state["status"] = "done" if returncode == 0 else "failed"
            state["returncode"] = returncode


@router.post("/ingest")
async def start_ingest(req: IngestRequest) -> RunInfo:
    """Returns as soon as the run is registered — the pipeline itself runs
    in a background thread (spawned below), never on this request's async
    task. A caller can poll GET /runs/{run_id} for progress, or not: the run
    proceeds either way, survives the browser tab closing, and only stops if
    this backend process itself restarts (see module docstring)."""
    if not req.youtube_url.strip():
        raise HTTPException(status_code=400, detail="youtube_url is required")
    if not req.student_id.strip():
        raise HTTPException(status_code=400, detail="student_id is required")

    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    log_path = RUN_LOG_DIR / f"{run_id}.log"
    started_at = time.time()
    video_title = await asyncio.to_thread(_fetch_youtube_title, req.youtube_url)

    with _runs_lock:
        _runs[run_id] = {
            "status": "running",
            "started_at": started_at,
            "returncode": None,
            "log_path": log_path,
            "video_title": video_title,
        }

    cmd = _build_command(req)
    threading.Thread(
        target=_run_worker,
        args=(run_id, cmd, log_path, req.student_id, req.subject or "", video_title, req.youtube_url),
        daemon=True,
    ).start()

    return RunInfo(run_id=run_id, status="running", started_at=started_at, log_tail="", video_title=video_title)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> RunInfo:
    with _runs_lock:
        state = _runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown run_id (or the backend restarted since it started)")

    log_path: Path = state["log_path"]
    tail = ""
    if log_path.exists():
        text = log_path.read_text(errors="replace")
        tail = text[-_LOG_TAIL_CHARS:]

    return RunInfo(
        run_id=run_id,
        status=state["status"],
        started_at=state["started_at"],
        returncode=state["returncode"],
        log_tail=tail,
        video_title=state.get("video_title", ""),
    )
