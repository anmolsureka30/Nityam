"""Centralized model configuration.

Model ids drift fast — this project has already shipped two silent
regressions from a stale/hallucinated id (see
project_documentation/memory_nityam_architecture/README.md's "Resolved via
LLM-as-judge review" section). Both ids below were verified live against
`client.models.list()` on 2026-08-26, not recalled from training data.
Re-run that listing before trusting them again if much time has passed:

    uv run --with google-genai python -c "
    from google import genai
    client = genai.Client()
    for m in client.models.list():
        print(m.name)
    "
"""

LIVE_MODEL = "gemini-3.1-flash-live-preview"
"""VoiceAgent — native audio, bidirectional (run_live) streaming."""

REASONING_MODEL = "gemini-3.7-flash"
"""TutorAgent and ArtifactAgent — text/tool reasoning, run via run_async
through the mode='single_turn' delegation path."""

import os

from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT = os.environ.get("GCP_PROJECT", "nityam-506707")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "smriti")
"""A named, non-default database — kept separate from
sub_modules_examples/memory_storage_testbed's own `smriti-testbed`
(project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md)."""
GCS_BUCKET = os.environ.get("GCS_BUCKET", "nityam-506707-tutor-artifacts")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
"""Workflow-tier write-through mirror (memory_layer.md §5). Local Redis for
now; real Memorystore is a deployment-time decision, not a code change —
see google_cloud_storage_integration.md §5.4."""
SESSION_IDLE_TIMEOUT_SECONDS = int(os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS", str(30 * 60)))
"""How long a session can go without a log_turn/log_artifact_evidence call
before the idle-timeout watcher (Task 7) auto-closes it. 30 minutes is a
starting value, not derived from a product requirement — tune via env var."""
