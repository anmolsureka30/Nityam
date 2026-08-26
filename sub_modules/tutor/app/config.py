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
