"""Cloud Run Job entrypoint: run a Shruti ingest, then report the result to
Nityam's backend over the authenticated sync webhook.

See docs/superpowers/specs/2026-08-30-cloud-run-deployment-design.md §4 for
why this exists: once Shruti runs as its own Cloud Run Job, it no longer
shares a filesystem or process with the Nityam backend, so the old path
(backend/app/shruti_routes.py reading this run's own stdout for a
SHRUTI_RESULT_JSON: marker line) no longer applies. This script is the
Job's own CMD — the interactive `shruti ingest` CLI command (shruti/cli.py)
is completely unaffected and still works exactly as before for a person at
a terminal; this only runs when NITYAM_SHRUTI_MODE=cloud_run_job triggers a
Job execution, never as a side effect of the CLI.

Ingest parameters arrive as container env var overrides (set by
backend/app/shruti_routes.py::_trigger_job), not CLI flags, because a Job
execution has no terminal to prompt at.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

    print(f"Downloading {youtube_url} ...")
    video_path = _download_youtube(youtube_url)
    print(f"Downloaded to {video_path}")

    from google import genai

    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN") or os.environ.get("GOOGLE_API_KEY")
    if not vertex_key:
        print("Neither GOOGLE_OAUTH_ACCESS_TOKEN nor GOOGLE_API_KEY is set", file=sys.stderr)
        sys.exit(1)
    client = genai.Client(vertexai=True, api_key=vertex_key)

    from shruti.ingest import run_ingest

    summary = asyncio.run(run_ingest(
        video_path, client,
        subject=subject or None,
        grade=int(grade) if grade else None,
        chapter=chapter or None,
    ))

    wiki_dir = Path("vault/wiki")
    concepts = []
    for slug in summary.get("concept_ids", []):
        path = wiki_dir / f"{slug}.md"
        if path.exists():
            concepts.append({"slug": slug, "wiki_markdown": path.read_text()})
        else:
            print(f"warning: wiki page missing for concept {slug!r} ({path})", file=sys.stderr)

    if not concepts:
        print("no concepts produced — nothing to sync, exiting cleanly")
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
