"""ArtifactAgent — turns a pedagogical need into one interactive artifact.

Wraps sub_modules_examples/artifact_generator's spec → Gemini → IR → validate
pipeline as a mode='single_turn' sub-agent. It never speaks to the student:
TutorAgent hands it a brief, it returns an artifact id, and TutorAgent does the
talking.

Two differences from the sub-module's own `--live` path:

  * **It returns the IR, not HTML.** The sub-module renders a standalone file
    because it has no app to live in; here the frontend mounts the artifact
    runtime against the IR directly, so it inherits the notebook's design
    tokens instead of sitting in an iframe.
  * **It never calls sys.exit().** `generator.generate_live` does, on a missing
    key or SDK — fine for a CLI, fatal for a server mid-lesson. So the
    generate-validate-retry loop is reimplemented here against the same
    `_build_prompt` and the same validator, and falls back to the golden IR the
    same way. A student never sees an unvalidated artifact.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import artifacts_gcs, config, logs, sessions
from app.agents.specialist_runner import SpecialistRunner, delegate
from app.canvas import doc as D
from app.memory.tools import get_dpm, get_teaching_memory, log_artifact_evidence

log = logging.getLogger("nityam.artifact")

# backend/app/agents/ -> backend/app -> backend -> repo root
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_ARTIFACT_GEN = os.path.join(_REPO_ROOT, "sub_modules_examples", "artifact_generator")
_GEN_DIR = os.path.join(_ARTIFACT_GEN, "generate")
if _GEN_DIR not in sys.path:
    sys.path.insert(0, _GEN_DIR)

_SCHEMA = os.path.join(_ARTIFACT_GEN, "ir", "schema.json")

MAX_ATTEMPTS = 2


def _generate_ir(spec) -> tuple[dict, str]:
    """spec -> validated IR. Returns (ir, provenance)."""
    import generator
    import validate

    def gate(candidate):
        return validate.validate(candidate, _SCHEMA)

    try:
        from google import genai
    except ImportError:
        ir, _ = generator.generate_mock(spec)
        return ir, "mock (google-genai not installed)"

    # No api_key argument: auth.configure() has already put this process on
    # the right platform (express mode, ADC, or AI Studio), and passing a key
    # here would override that inconsistently.
    try:
        client = genai.Client()
    except Exception as exc:  # noqa: BLE001 - any client failure means fall back
        log.warning("no Gemini client for artifact generation: %s", exc)
        ir, _ = generator.generate_mock(spec)
        return ir, f"mock (no client: {type(exc).__name__})"

    prompt = generator._build_prompt(spec)
    model = config.reasoning_model()
    errors: list[str] | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        message = prompt
        if errors:
            message += (
                "\n\n## Your previous attempt FAILED validation\n"
                + "\n".join("- " + e for e in errors)
                + "\nEmit a corrected IR that fixes every one of these."
            )
        try:
            response = client.models.generate_content(
                model=model,
                contents=message,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("artifact generation call failed: %s", exc)
            detail = f"{type(exc).__name__}"
            if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                detail = "rate limited (429)"
            ir, _ = generator.generate_mock(spec)
            return ir, f"mock fallback — the generation call failed: {detail}"

        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            raw = raw[4:] if raw.startswith("json") else raw
        try:
            ir = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors = [f"response was not valid JSON: {exc}"]
            continue

        report = gate(ir)
        if report.ok:
            return ir, f"live ({model}, attempt {attempt})"
        errors = report.errors
        log.info("artifact IR rejected on attempt %s: %s", attempt, errors[:3])

    ir, _ = generator.generate_mock(spec)
    return ir, (
        f"mock fallback — {MAX_ATTEMPTS} generated IR(s) failed validation"
    )


async def create_artifact(
    intent: str,
    concept_ids: list[str],
    learning_outcome: str,
    target_misconception: str,
    interest: str,
    tool_context: ToolContext,
) -> dict:
    """Build one interactive artifact and put it on the student's page.

    This call takes the full generation time (up to ~30 seconds) — that is
    expected. ArtifactAgent's whole turn is already non-blocking from
    VoiceAgent's side (ask_artifact is response_scheduling=WHEN_IDLE), so
    there is no need for a separate fire-and-forget layer inside this call
    any more.

    You configure it; you never write the physics or the rendering. Call
    this once per request.

    Args:
        intent: What pedagogical move this artifact makes, e.g. "let the
            student discover that range peaks at 45 degrees by exploring,
            not being told".
        concept_ids: Concept ids this targets, e.g. ["projectile.horizontal_range"].
        learning_outcome: The one thing the student should walk away understanding.
        target_misconception: The specific wrong belief this should surface and
            correct. Pass "" if there isn't one.
        interest: The student's theme to personalise with, e.g. "cricket".
            Pass "plain" if unknown.

    Returns:
        dict with "status": "landed", "block_id", "title" — or
        {"status": "failed", "error": ...} if generation could not complete.
    """
    from spec import ArtifactSpec

    session_id = tool_context.state.get("session_id") or "unknown"
    artifact_spec = ArtifactSpec(
        intent=intent,
        concept_ids=list(concept_ids),
        learning_outcome=learning_outcome,
        target_misconception=target_misconception,
        student={"interest": interest or "plain"},
    )

    try:
        ir, provenance = await asyncio.to_thread(_generate_ir, artifact_spec)
    except Exception as exc:  # noqa: BLE001 - report failure, never crash the turn
        log.exception("background artifact generation failed")
        return {"status": "failed", "error": type(exc).__name__}

    artifact_id = ir.get("artifact_id") or f"artifact-{uuid.uuid4().hex[:8]}"
    state = sessions.get(session_id)
    block = D.ArtifactBlock(id=state.mint("b_art"), artifactId=artifact_id, ir=ir)
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("finished artifact rejected by the board: %s", exc)
        return {"status": "failed", "error": str(exc)}

    try:
        await asyncio.to_thread(artifacts_gcs.save_artifact_to_gcs, artifact_id, ir)
    except Exception:  # noqa: BLE001 - durability is a bonus, not a lesson-blocker
        log.warning("artifact %s failed to persist to GCS", artifact_id, exc_info=True)

    log.info("artifact %s mounted as %s — %s", artifact_id, block.id, provenance)
    log.debug("artifact IR: %s", json.dumps(ir, ensure_ascii=False))
    logs.count("artifact landed")
    return {
        "status": "landed",
        "block_id": block.id,
        "title": ir.get("title") or "the simulation",
    }


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Call create_artifact IMMEDIATELY, in your first message, exactly once. Do not
look anything up first. get_dpm and get_teaching_memory are here only for the
rare case where the request is too thin to configure an artifact at all —
every call you make is another few seconds before the build even starts, and
you have already been given the recent conversation and the request itself.

Then report back a short, plain-language line about what landed — the
title and what the student can do with it, as if telling a colleague. Do
not describe the artifact in exhaustive detail — the visual IS the
explanation.

When an artifact reports an interaction event back to you (e.g. it
discovered the optimum, or it exhibited a known misconception's behaviour),
call log_artifact_evidence with that event and the artifact_id — this is the
only way that interaction becomes part of this student's permanent record.
"""


def build_artifact_agent() -> LlmAgent:
    return LlmAgent(
        name="ArtifactAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Generates one interactive artifact (diagram or simulation) for "
            "a specific pedagogical need and puts it on the board. Call "
            "with a clear description of what the student should discover "
            "or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )


_RUNNER = SpecialistRunner("nityam-artifact", build_artifact_agent)


async def ask_artifact(bridge: str, request: str, tool_context: ToolContext):
    """Commission one interactive artifact.

    Returns at once and keeps you talking while ArtifactAgent builds it — you
    will be told when it lands, at a natural pause. A build takes tens of
    seconds; do not announce the call, and do not stop and wait.

    Args:
        bridge: One short sentence in your own voice, said as you call.
        request: What the artifact is for, in your own words — the pedagogical
            move it makes, the concept ids it targets, the one thing the
            student should walk away understanding, and the specific wrong
            belief it should surface. Be concrete.
    """
    async for chunk in delegate(
        "artifact", _RUNNER, request, tool_context,
        transcript_n=10,
        done_default="The simulation is ready.",
        error_text="The simulation could not be built this time.",
    ):
        yield chunk
