"""ArtifactAgent — wraps sub_modules/artifact_generator's
spec -> IR -> validate -> render pipeline as a single_turn ADK sub-agent
(memory_layer.md §3, architecture.md §2).
"""
from __future__ import annotations

import os
import sys
import uuid

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.memory.tools import get_dpm, get_teaching_memory, log_artifact_evidence

_TUTOR_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARTIFACT_GEN = os.path.join(os.path.dirname(_TUTOR_ROOT), "artifact_generator")
sys.path.insert(0, os.path.join(_ARTIFACT_GEN, "generate"))

ARTIFACTS_OUT = os.path.join(_TUTOR_ROOT, "app", "artifacts_out")


def create_artifact(
    intent: str,
    concept_ids: list[str],
    learning_outcome: str,
    target_misconception: str,
    interest: str,
    tool_context: ToolContext,
) -> dict:
    """Generate one interactive artifact (diagram, simulation, or quiz) for
    the student — the model configures it, it never writes the physics or
    the rendering code (sub_modules/artifact_generator/README.md).

    Args:
        intent: What pedagogical move this artifact makes, e.g. "let the
            student discover that range peaks at 45 degrees by exploring,
            not being told".
        concept_ids: Concept ids this artifact targets, e.g.
            ["projectile.horizontal_range"].
        learning_outcome: The one thing the student should walk away
            understanding.
        target_misconception: The specific wrong belief this artifact should
            surface and correct. Pass "" if there isn't one.
        interest: The student's theme to personalize with, e.g. "cricket".
            Pass "plain" if unknown.

    Returns:
        dict with "artifact_id" and "url" — the frontend mounts the artifact
        at this URL — or {"error": ...} if it failed validation.
    """
    import generator
    import validate
    from render import render_html
    from spec import ArtifactSpec

    artifact_spec = ArtifactSpec(
        intent=intent,
        concept_ids=concept_ids,
        learning_outcome=learning_outcome,
        target_misconception=target_misconception,
        student={"interest": interest},
    )
    schema_path = os.path.join(_ARTIFACT_GEN, "ir", "schema.json")
    ir, source = generator.generate_live(
        artifact_spec,
        lambda candidate: validate.validate(candidate, schema_path),
        model=config.REASONING_MODEL,
    )
    report = validate.validate(ir, schema_path)
    if not report.ok:
        return {"error": "artifact failed validation", "details": report.errors}

    passed = sum(1 for _, ok, _ in report.checks if ok)
    artifact_id = ir.get("artifact_id") or f"artifact-{uuid.uuid4().hex[:8]}"
    html = render_html(ir, interest, {
        "source": source,
        "spec": intent,
        "checks_passed": passed,
        "checks_total": len(report.checks),
    })

    os.makedirs(ARTIFACTS_OUT, exist_ok=True)
    with open(os.path.join(ARTIFACTS_OUT, f"{artifact_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    generated = tool_context.state.get("artifacts_generated", [])
    generated.append(artifact_id)
    tool_context.state["artifacts_generated"] = generated

    return {"artifact_id": artifact_id, "url": f"/artifacts/{artifact_id}.html"}


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Read get_dpm and get_teaching_memory to calibrate: a student who is "partial"
on a concept needs a more scaffolded artifact than one who is "known". Call
create_artifact exactly once with a clear intent, then report back only the
artifact_id and url — do not describe the artifact in prose, the visual IS
the explanation.

When an artifact reports an interaction event back to you (e.g. it discovered
the optimum, or it exhibited a known misconception's behaviour), call
log_artifact_evidence with that event and the artifact_id — this is the only
way that interaction becomes part of this student's permanent record.
"""


def build_artifact_agent() -> LlmAgent:
    return LlmAgent(
        name="ArtifactAgent",
        model=config.REASONING_MODEL,
        mode="single_turn",
        description=(
            "Generates one interactive artifact (diagram, simulation, or "
            "quiz) for a specific pedagogical need. Call with a clear "
            "description of what the student should discover or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )
