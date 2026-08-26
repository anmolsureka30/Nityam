"""Tests the parts of create_artifact() that don't need a live model call:
validation, rendering, file-writing, and the returned reference. The
generate_live() call itself is exercised only in the manual live-verification
step, since it needs a working Gemini API key with quota — here it's always
monkeypatched to return a canned (ir, source) tuple instead."""
import copy
import json
import os
import sys
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_TUTOR_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_ARTIFACT_GEN = os.path.join(os.path.dirname(_TUTOR_ROOT), "artifact_generator")
sys.path.insert(0, os.path.join(_ARTIFACT_GEN, "generate"))

import generator  # noqa: E402
import validate as validate_module  # noqa: E402
from render import render_html  # noqa: E402
from validate import Report, validate  # noqa: E402

from app.agents import artifact_agent  # noqa: E402


def _golden_ir():
    with open(os.path.join(_ARTIFACT_GEN, "examples", "lesson1_max_range.json")) as f:
        return json.load(f)


def make_tool_context(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


def test_golden_ir_validates_and_renders():
    ir = _golden_ir()

    report = validate(ir, os.path.join(_ARTIFACT_GEN, "ir", "schema.json"))
    assert report.ok, report.errors

    html = render_html(ir, "plain", {"source": "test", "spec": "test"})
    assert ir["artifact_id"] in html


def test_create_artifact_writes_html_and_returns_reference(monkeypatch, tmp_path):
    ir = _golden_ir()
    monkeypatch.setattr(generator, "generate_live", lambda *a, **k: (ir, "mock (golden IR)"))
    monkeypatch.setattr(artifact_agent, "ARTIFACTS_OUT", str(tmp_path))

    ctx = make_tool_context({})
    result = artifact_agent.create_artifact(
        intent="let the student discover the 45-degree optimum by exploring",
        concept_ids=["projectile.max_range"],
        learning_outcome="Range peaks at 45 degrees for a fixed launch speed.",
        target_misconception="",
        interest="plain",
        tool_context=ctx,
    )

    assert result == {
        "artifact_id": ir["artifact_id"],
        "url": f"/artifacts/{ir['artifact_id']}.html",
    }

    out_file = tmp_path / f"{ir['artifact_id']}.html"
    assert out_file.exists()
    assert ir["artifact_id"] in out_file.read_text(encoding="utf-8")

    assert ctx.state["artifacts_generated"] == [ir["artifact_id"]]


def test_create_artifact_appends_to_an_existing_artifacts_generated_list(monkeypatch, tmp_path):
    ir = _golden_ir()
    monkeypatch.setattr(generator, "generate_live", lambda *a, **k: (ir, "mock (golden IR)"))
    monkeypatch.setattr(artifact_agent, "ARTIFACTS_OUT", str(tmp_path))

    ctx = make_tool_context({"artifacts_generated": ["earlier-artifact"]})
    artifact_agent.create_artifact(
        intent="x",
        concept_ids=["c"],
        learning_outcome="y",
        target_misconception="",
        interest="plain",
        tool_context=ctx,
    )

    assert ctx.state["artifacts_generated"] == ["earlier-artifact", ir["artifact_id"]]


def test_create_artifact_falls_back_to_a_generated_id_when_ir_lacks_one(monkeypatch, tmp_path):
    ir = copy.deepcopy(_golden_ir())
    ir["artifact_id"] = ""  # falsy, but keeps the key so render_html's ir["artifact_id"] lookup is safe
    monkeypatch.setattr(generator, "generate_live", lambda *a, **k: (ir, "mock (golden IR)"))
    monkeypatch.setattr(artifact_agent, "ARTIFACTS_OUT", str(tmp_path))

    ctx = make_tool_context({})
    result = artifact_agent.create_artifact(
        intent="x",
        concept_ids=["c"],
        learning_outcome="y",
        target_misconception="",
        interest="plain",
        tool_context=ctx,
    )

    assert result["artifact_id"].startswith("artifact-")
    assert result["url"] == f"/artifacts/{result['artifact_id']}.html"
    assert (tmp_path / f"{result['artifact_id']}.html").exists()
    assert ctx.state["artifacts_generated"] == [result["artifact_id"]]


def test_create_artifact_returns_error_when_ir_fails_validation(monkeypatch, tmp_path):
    ir = _golden_ir()
    monkeypatch.setattr(generator, "generate_live", lambda *a, **k: (ir, "mock (golden IR)"))
    monkeypatch.setattr(artifact_agent, "ARTIFACTS_OUT", str(tmp_path))

    failing_report = Report()
    failing_report.err("invariant.argmax: peak was not at 45 degrees")
    monkeypatch.setattr(validate_module, "validate", lambda *a, **k: failing_report)

    ctx = make_tool_context({})
    result = artifact_agent.create_artifact(
        intent="x",
        concept_ids=["c"],
        learning_outcome="y",
        target_misconception="",
        interest="plain",
        tool_context=ctx,
    )

    assert result == {
        "error": "artifact failed validation",
        "details": failing_report.errors,
    }
    # nothing should have been written or recorded on a rejected artifact
    assert list(tmp_path.iterdir()) == []
    assert "artifacts_generated" not in ctx.state
