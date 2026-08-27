"""reflect()'s wire-schema conversion, with no model in the loop.

The bug this guards against: ReflectResult.operations used to be
`args: dict[str, Any]` as the schema handed straight to Gemini's structured
output. A JSON schema for `dict[str, Any]` gives the model no field names to
fill in, so live testing (against the sub_modules_examples/tutor sibling of
this file, same REFLECT_PROMPT/reflect() shape) showed Gemini reliably
returns `args: {}` for every operation — silently dropped by
apply_operations' TypeError guard. close_session looked like it worked but
never wrote anything. Fixed with a flat _ReflectOpWire schema converted back
to ReflectOp(op, args) by _to_reflect_op.

    .venv/bin/python -m tests.test_session_close
"""
from __future__ import annotations

from app.memory.schemas import DPMProfile, TeachingMemory
from app.session_close import ReflectResult, _ReflectOpWire, _to_reflect_op, apply_operations

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    # ------------------------------------- _to_reflect_op field selection
    wire = _ReflectOpWire(
        op="set_mastery", concept_id="projectile.range", mastery="known",
        strength="strong", evidence=["s1#2"],
        # fields belonging to other ops -- the wire schema has no way to
        # omit them, so they're always present and must not leak through.
        doubt="unrelated", note="unrelated", status="covered",
    )
    result = _to_reflect_op(wire)
    check(
        "set_mastery keeps only its own fields", result.op == "set_mastery" and result.args == {
            "concept_id": "projectile.range", "mastery": "known",
            "strength": "strong", "evidence": ["s1#2"],
        },
        str(result.args),
    )

    unset = _to_reflect_op(_ReflectOpWire(op="close_doubt", concept_id="projectile.range"))
    check("unset fields are omitted, not passed as None", unset.args == {"concept_id": "projectile.range"}, str(unset.args))

    # ------------------------------------------- apply_operations, end to end
    profile = DPMProfile(student_id="test_backend_student")
    memory = TeachingMemory(student_id="test_backend_student")
    result = ReflectResult(
        summary="",
        operations=[
            _to_reflect_op(_ReflectOpWire(
                op="set_mastery", concept_id="projectile.range", mastery="known",
                strength="strong", evidence=["s1#1"],
            )),
            _to_reflect_op(_ReflectOpWire(
                op="open_doubt", concept_id="projectile.range", doubt="uses u not u*cos(theta)",
                correct_understanding="R = u^2 sin(2theta)/g", evidence=["s1#1"],
            )),
        ],
    )
    profile, memory = apply_operations(profile, memory, result)
    check("set_mastery op actually wrote a weakness", profile.weaknesses.get("projectile.range") is not None and profile.weaknesses["projectile.range"].mastery == "known")
    check("open_doubt op actually wrote a doubt", len(memory.open_doubts) == 1 and memory.open_doubts[0].concept_id == "projectile.range")

    # A missing required field (evidence) must still be dropped, not raised.
    profile2 = DPMProfile(student_id="test_backend_student_2")
    memory2 = TeachingMemory(student_id="test_backend_student_2")
    malformed = ReflectResult(
        summary="",
        operations=[_to_reflect_op(_ReflectOpWire(op="set_mastery", concept_id="x"))],
    )
    profile2, memory2 = apply_operations(profile2, memory2, malformed)
    check("a malformed op (missing required fields) is dropped, not raised", profile2.weaknesses == {})

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
