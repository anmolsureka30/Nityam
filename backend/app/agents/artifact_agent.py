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

    try:
        artifacts_gcs.save_artifact_to_gcs(artifact_id, ir)
    except Exception:  # noqa: BLE001 - durability is a bonus, not a lesson-blocker
        log.warning("artifact %s failed to persist to GCS", artifact_id, exc_info=True)

    log.info("artifact %s mounted as %s — %s", artifact_id, block.id, provenance)
    log.debug("artifact IR: %s", json.dumps(ir, ensure_ascii=False))
    logs.count("artifact landed")
    title = ir.get("title") or "the simulation"

    # Two messages, deliberately different in kind. The injection is FACT — it
    # is what lets her answer "has it loaded yet?" truthfully a minute later,
    # which is exactly the question she invented five answers to in an earlier
    # session. The nudge below is the INSTRUCTION to interrupt herself and say
    # it has arrived.
    controls = ", ".join(
        c.get("id", "") for c in (ir.get("controls") or []) if c.get("id")
    )
    sessions.inject(
        session_id,
        f"[BOARD UPDATED, context only — do not announce it or reply to this. "
        f"The simulation “{title}” is now on the student's page as {block.id}"
        + (f", with controls {controls}" if controls else "")
        + ". It is genuinely there; if they ask later whether it loaded, the "
        "answer is yes and you may say so without checking.]",
    )
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
    log.debug("artifact spec: %s", artifact_spec)
    logs.count("artifact started")
    return {
        "status": "building",
        "eta_seconds": 30,
        "next": (
            "Say one line that it is coming, then IMMEDIATELY teach something "
            "in the same turn — ask them to predict what the simulation will "
            "show, work a number, or set a checkpoint. Do not end your turn "
            "with an open invitation like 'let me know when you're ready': that "
            "hands the lesson back to a student who came here not to have to "
            "run it. You will be told the moment it lands."
        ),
    }


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Call create_artifact IMMEDIATELY, in your first message, exactly once. Do not
look anything up first. get_dpm and get_teaching_memory are here only for the
rare case where the tutor's brief is too thin to configure an artifact at all —
every call you make is another three seconds before the build even starts, and
the tutor already has this student's record in its own prompt and has put what
matters into the brief.

Then report back ONLY the artifact_id, block_id and title. Do not describe the
artifact in prose — the visual IS the explanation, and the tutor will do the
talking. You never address the student.

When an artifact reports an interaction event back to you (e.g. it discovered
the optimum, or it exhibited a known misconception's behaviour), call
log_artifact_evidence with that event and the artifact_id — this is the only
way that interaction becomes part of this student's permanent record.
"""


def build_artifact_agent(mode: str | None = "single_turn") -> LlmAgent:
    """mode='single_turn': as a sub-agent (kept for text-mode testing).
    mode=None: valid as a root_agent, which is how commission_artifact runs it.

    ADK type-checks the difference — google/adk/runners.py: "LlmAgent as root
    agent must have mode='chat' or 'task'" — exactly as build_tutor_agent does.
    """
    return LlmAgent(
        name="ArtifactAgent",
        model=config.reasoning_model(),
        mode=mode,
        description=(
            "Generates one interactive artifact (diagram, simulation, or "
            "quiz) for a specific pedagogical need and puts it on the board. "
            "Call with a clear description of what the student should discover "
            "or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )


# ------------------------------------------------- running it out of the way

_runner = None
_sessions_svc = None
_known: set[str] = set()

ARTIFACT_APP = "nityam-artifact"


def _agent_runner():
    """ArtifactAgent in its own Runner, built once.

    Same construction as brain.runner() (app/agents/brain.py), for the same
    reason: an agent reached this way runs as an ordinary invocation, so nothing
    depends on nested-sub-agent machinery.
    """
    global _runner, _sessions_svc
    if _runner is None:
        from google.adk.apps import App
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        _sessions_svc = InMemorySessionService()
        _runner = Runner(
            app=App(name=ARTIFACT_APP, root_agent=build_artifact_agent(mode=None)),
            session_service=_sessions_svc,
        )
        log.info("artifact runner built")
    return _runner


async def _consult(session_id: str, student_id: str, brief: str) -> None:
    """Run ArtifactAgent to completion, off the tutor's critical path."""
    from google.genai import types

    _agent_runner()
    key = f"{session_id}:artifact"
    if key not in _known:
        if not await _sessions_svc.get_session(
            app_name=ARTIFACT_APP, user_id=student_id, session_id=key
        ):
            await _sessions_svc.create_session(
                app_name=ARTIFACT_APP, user_id=student_id, session_id=key,
                state={"session_id": session_id, "student_id": student_id},
            )
        _known.add(key)

    try:
        async for event in _agent_runner().run_async(
            user_id=student_id,
            session_id=key,
            new_message=types.Content(role="user", parts=[types.Part(text=brief)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.function_call:
                    log.info("→ TOOL CALL %s calls %s", event.author,
                             part.function_call.name)
    except Exception as exc:  # noqa: BLE001 - a failed artifact must not end the lesson
        log.exception("ArtifactAgent failed")
        sessions.nudge(
            session_id,
            "[The simulation you asked for could not be built "
            f"({type(exc).__name__}). Tell the student briefly and carry on "
            "teaching without it. Do not try again.]",
        )


async def commission_artifact(brief: str, tool_context: ToolContext) -> dict:
    """Commission one interactive artifact from ArtifactAgent. Returns IMMEDIATELY.

    ArtifactAgent is a separate specialist with its own model: it reads your
    brief, configures the artifact, and puts it on the student's page. None of
    that happens while you wait. You get control back at once and you must keep
    teaching — you will be told the moment it lands.

    Args:
        brief: What the artifact is for, in your own words — the pedagogical
            move it makes, the concept ids it targets, the one thing the student
            should walk away understanding, and the specific wrong belief it
            should surface. Be concrete: "let them discover that range peaks at
            45 degrees by exploring, not being told; they currently think
            throwing harder is what matters; concepts
            projectile.horizontal_range; theme cricket" beats "a projectile
            simulation".

    Returns:
        dict with "status": "commissioned" — and what to do meanwhile.
    """
    session_id = tool_context.state.get("session_id") or "unknown"
    student_id = tool_context.state.get("student_id") or "demo_student"

    # create_task, not await: this is the whole point. ArtifactAgent needs two
    # model round trips of its own — 7.1 seconds, measured — and as a
    # mode='single_turn' sub-agent the tutor blocked on every one of them before
    # generation had even begun. Now they overlap the tutor's own next round
    # trip and the student's next utterance.
    task = asyncio.get_running_loop().create_task(
        _consult(session_id, student_id, brief)
    )
    sessions.track(session_id, task)

    log.info("artifact commissioned for %s: %s", session_id, brief[:120])
    logs.count("artifact commissioned")
    return {
        "status": "commissioned",
        "eta_seconds": 30,
        "next": (
            "ArtifactAgent has the brief and is working. Do NOT wait and do NOT "
            "go quiet: say one line that it is coming, then teach something in "
            "this same turn — ask them to predict what it will show, work a "
            "number, or set a checkpoint. You will be told the moment it lands."
        ),
    }
