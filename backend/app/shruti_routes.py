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

This file touches no tutor/agent/memory code and is not imported by anything
under app/agents/ or app/memory/ — the only integration point is the two
routes below plus one `app.include_router(...)` line in main.py.

State is a plain in-process dict: this backend is a single dev process
(uvicorn --reload notwithstanding — a code reload restarts the whole worker,
which is already true of every other transient state here, e.g. app/sessions.py's
in-memory session table). A run in progress does not survive a backend
restart; that is an acceptable limit for a best-effort dashboard feature, not
a silent bug — the frontend surfaces "unknown run" rather than hanging if it
polls a run_id that state doesn't remember.
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/shruti")

# backend/app/shruti_routes.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SHRUTI_DIR = REPO_ROOT / "sub_modules_examples" / "shruti"
RUN_LOG_DIR = SHRUTI_DIR / ".local" / "dashboard_runs"

RunStatus = Literal["running", "done", "failed"]


class IngestRequest(BaseModel):
    youtube_url: str
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None


class RunInfo(BaseModel):
    run_id: str
    status: RunStatus
    started_at: float
    returncode: int | None = None
    log_tail: str


_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()

# How much of the log to hand back per poll — enough to read the last few
# stage transitions without the response growing unbounded on a long run.
_LOG_TAIL_CHARS = 6000


def _build_command(req: IngestRequest) -> list[str]:
    """Exactly the command the CLI's own --help text tells a person to run —
    see shruti/cli.py's `ingest` docstring and its "run with `uv run
    --env-file .env shruti ingest`" hint when credentials are missing."""
    cmd = ["uv", "run", "--env-file", ".env", "shruti", "ingest", "--url", req.youtube_url]
    if req.subject:
        cmd += ["--subject", req.subject]
    if req.grade is not None:
        cmd += ["--grade", str(req.grade)]
    if req.chapter:
        cmd += ["--chapter", req.chapter]
    return cmd


def _run_worker(run_id: str, cmd: list[str], log_path: Path) -> None:
    try:
        with log_path.open("w") as log_file:
            log_file.write(f"$ {' '.join(cmd)}\n\n")
            log_file.flush()
            proc = subprocess.Popen(
                cmd, cwd=str(SHRUTI_DIR), stdout=log_file, stderr=subprocess.STDOUT,
            )
            returncode = proc.wait()
    except OSError as e:
        # e.g. `uv` not on PATH in this process's environment — a real,
        # reportable failure, not a crash of the polling endpoint.
        with log_path.open("a") as log_file:
            log_file.write(f"\nFailed to start: {e}\n")
        returncode = -1

    with _runs_lock:
        state = _runs.get(run_id)
        if state is not None:
            state["status"] = "done" if returncode == 0 else "failed"
            state["returncode"] = returncode


@router.post("/ingest")
async def start_ingest(req: IngestRequest) -> RunInfo:
    if not req.youtube_url.strip():
        raise HTTPException(status_code=400, detail="youtube_url is required")

    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    log_path = RUN_LOG_DIR / f"{run_id}.log"
    started_at = time.time()

    with _runs_lock:
        _runs[run_id] = {
            "status": "running",
            "started_at": started_at,
            "returncode": None,
            "log_path": log_path,
        }

    cmd = _build_command(req)
    threading.Thread(target=_run_worker, args=(run_id, cmd, log_path), daemon=True).start()

    return RunInfo(run_id=run_id, status="running", started_at=started_at, log_tail="")


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
    )
