"""Endpoints called by other Google Cloud resources, not by browsers.

Today: the Shruti Cloud Run Job, reporting back what it extracted. Not under
app/memory_routes.py's `/memory` prefix because these aren't reads a
student's browser ever makes — a different trust boundary (service-to-
service ID tokens, not Firebase user tokens) deserves a different module,
not just a different route. See docs/superpowers/specs/
2026-08-30-cloud-run-deployment-design.md §4 for why this exists at all.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from app.memory import shruti_sync

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
    The main service stays "allow unauthenticated" for real student traffic
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
    """Called once by the Shruti Cloud Run Job's entrypoint (see
    sub_modules_examples/shruti/shruti/job_entrypoint.py) after an ingest run
    finishes — the live equivalent, once Shruti and Nityam are no longer
    co-located, of app/shruti_routes.py's in-process
    shruti_sync.sync_ingested_recording() call."""
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
