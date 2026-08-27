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

from app import config, sessions
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
            break

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
    return ir, "mock fallback (live rejected by the validator)"


async def _build(session_id: str, spec, interest: str, placeholder_id: str) -> None:
    """Generate the artifact off the conversation's critical path.

    `_generate_ir` is a synchronous Gemini call plus a validation sweep — thirty
    seconds or so. Awaiting it inside the tool meant the student sat in silence
    for that whole time, and running it as a bare task would be worse: a
    blocking call on the event loop freezes the audio stream too. So it goes to
    a thread, and the conversation carries on without it.
    """
    try:
        ir, provenance = await asyncio.to_thread(_generate_ir, spec)
    except Exception as exc:  # noqa: BLE001 - a failed artifact must not end the lesson
        log.exception("background artifact generation failed")
        sessions.nudge(
            session_id,
            "[The simulation you asked for could not be built "
            f"({type(exc).__name__}). Tell the student briefly and carry on "
            "teaching without it. Do not try again.]",
        )
        return

    artifact_id = ir.get("artifact_id") or placeholder_id
    state = sessions.get(session_id)
    block = D.ArtifactBlock(id=state.mint("b_art"), artifactId=artifact_id, ir=ir)
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("finished artifact rejected by the board: %s", exc)
        return

    log.info("artifact %s mounted as %s — %s", artifact_id, block.id, provenance)
    title = ir.get("title") or "the simulation"
    sessions.nudge(
        session_id,
        f"[The interactive artifact you asked for is now on the student's page: "
        f"“{title}” (block {block.id}). Whatever you are in the middle of, bring "
        f"them to it now — tell them it is ready and what to do with it. One "
        f"sentence.]",
    )


async def create_artifact(
    intent: str,
    concept_ids: list[str],
    learning_outcome: str,
    target_misconception: str,
    interest: str,
    tool_context: ToolContext,
) -> dict:
    """Start building one interactive artifact. Returns IMMEDIATELY.

    Generation takes around thirty seconds and happens in the background. You
    do NOT wait for it and you must NOT stop teaching: say you are building it,
    then carry on with something useful — ask them a question, work an example,
    set a checkpoint. You will be told the moment it appears on their page.

    You configure it; you never write the physics or the rendering. Call this
    once per request.

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
        dict with "status": "building" — and instructions on what to do while
        it builds.
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
    placeholder = f"artifact-{uuid.uuid4().hex[:8]}"

    # async def, not def: a sync tool can be dispatched into a thread by the
    # framework, where there is no running loop to attach a background task to —
    # and the fallback would be to generate synchronously, which is the very
    # thing this exists to avoid. Declaring it async guarantees the loop.
    task = asyncio.get_running_loop().create_task(
        _build(session_id, artifact_spec, interest or "plain", placeholder)
    )
    sessions.track(session_id, task)
    generated = list(tool_context.state.get("artifacts_generated", []))
    generated.append(placeholder)
    tool_context.state["artifacts_generated"] = generated

    log.info("artifact build started for session %s", session_id)
    return {
        "status": "building",
        "eta_seconds": 30,
        "next": (
            "Do not wait and do not go quiet. Tell the student it is coming, "
            "then keep teaching — a question, a worked step, or a checkpoint. "
            "You will be told when it lands."
        ),
    }


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Read get_dpm and get_teaching_memory to calibrate: a student who is "partial"
on a concept needs a more scaffolded artifact than one who is "known". Call
create_artifact exactly once with a clear intent.

Then report back ONLY the artifact_id, block_id and title. Do not describe the
artifact in prose — the visual IS the explanation, and the tutor will do the
talking. You never address the student.

When an artifact reports an interaction event back to you (e.g. it discovered
the optimum, or it exhibited a known misconception's behaviour), call
log_artifact_evidence with that event and the artifact_id — this is the only
way that interaction becomes part of this student's permanent record.
"""


def build_artifact_agent() -> LlmAgent:
    return LlmAgent(
        name="ArtifactAgent",
        model=config.reasoning_model(),
        mode="single_turn",
        description=(
            "Generates one interactive artifact (diagram, simulation, or "
            "quiz) for a specific pedagogical need and puts it on the board. "
            "Call with a clear description of what the student should discover "
            "or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )
