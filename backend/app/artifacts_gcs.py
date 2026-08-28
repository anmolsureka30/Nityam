"""Durable storage for generated artifact IR, in Cloud Storage.

ArtifactAgent's own board write already keeps the IR in the live board for
the running session (app/agents/artifact_agent.py:_build) — this is the copy
that survives a reload or a restart, keyed by artifact_id.

Not routed through ADK's tool_context.save_artifact(): _build() runs as a
detached background asyncio task (see its own docstring — generation is
spawned off the conversation's critical path), so by the time it finishes,
the tool invocation that spawned it has already returned, and ToolContext's
write methods are scoped to a live invocation. A plain google-cloud-storage
client sidesteps that lifetime question entirely.
"""
from __future__ import annotations

import json

from google.cloud import storage

from app import config


def _blob(artifact_id: str) -> storage.Blob:
    client = storage.Client()
    bucket = client.bucket(config.GCS_BUCKET)
    return bucket.blob(f"artifacts/{artifact_id}.json")


def save_artifact_to_gcs(artifact_id: str, ir: dict) -> None:
    _blob(artifact_id).upload_from_string(
        json.dumps(ir, ensure_ascii=False), content_type="application/json",
    )


def read_artifact_from_gcs(artifact_id: str) -> dict:
    return json.loads(_blob(artifact_id).download_as_text())


def delete_artifact_from_gcs(artifact_id: str) -> None:
    _blob(artifact_id).delete()
