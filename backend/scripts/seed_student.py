"""Reset one REAL signed-in student to a clean, demonstrable state.

    .venv/bin/python -m scripts.seed_student            # wipe, then seed
    .venv/bin/python -m scripts.seed_student --clear    # wipe only
    .venv/bin/python -m scripts.seed_student --student <uid> --email <addr>

WHAT IT DOES. Deletes every session log for the student, resets their
dpm_profile and teaching_memory, and writes back TWO finished sessions plus the
record those sessions produced. Idempotent: run it as often as you like and the
state is identical afterwards, which is what makes it usable before a demo.

The two sessions are seeded WITH before/after snapshots, so /sessions/:id has
something to show. That is the whole reason this exists in its current form —
a session log written before recaps existed renders as "no record kept", which
is honest but demonstrates nothing.

WHY THE CONTENT IS NOT INVENTED. Both sessions are taken from real recorded
ones (backend/logs/2026-08-30_02-46-17 and 03-37-59): the student really did
answer "u sin theta" when asked for the horizontal component, really did recall
the time-of-flight formula unprompted, really did reach sin(2θ) with prompting,
and really did fail a checkpoint on vector resolution. The memory layer's
invariant is that a claim about a student resolves back to a moment that
happened; seeding plausible fiction would break the one property it exists to
protect.

CONCEPT IDS ARE THE REAL ONES, checked against store.list_concept_ids(). This
matters: `seed_demo_data.py` cites `projectile.horizontal_range` twice and no
such concept is in the corpus, so those weaknesses retrieve nothing and vanish
from the brief without any error.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

# BEFORE app.memory.store: store.py picks its backend off NITYAM_STORE at
# IMPORT time, so loading .env afterwards silently seeds sqlite while the
# running app reads Firestore. That happened on this script's first run.
from app.auth import load_env

load_env()

from app.memory import store  # noqa: E402
from app.memory.schemas import (  # noqa: E402
    CoveredConcept,
    DPMProfile,
    OpenDoubt,
    Persona,
    SessionLog,
    TeachingMemory,
    TeachingStyle,
    Turn,
    Weakness,
)

DEFAULT_STUDENT = "Xu2su777GANXJppk3kt3n8fjda42"
DEFAULT_EMAIL = "arnav.prasad999918@gmail.com"

VECTOR = "projectile.vector_resolution"
FLIGHT = "projectile.time_of_flight"
HEIGHT = "projectile.maximum_height"
MOTION = "projectile.projectile_motion"

PERSONA = Persona(
    preferred_pace="moderate",
    # He asked for English out loud, mid-session. Recording it is what stops
    # the next session opening in Hindi again.
    language_mix="English, with Hindi only if the student switches first",
    interests=["cricket"],
)

FIRST = "s_seed_1"
SECOND = "s_seed_2"


def _first_session(student_id: str, when: datetime) -> tuple[SessionLog, DPMProfile, TeachingMemory]:
    """Four days ago. A cold start: nothing on record, two concepts land."""
    before_dpm = DPMProfile(student_id=student_id, persona=PERSONA)
    before_tm = TeachingMemory(student_id=student_id, syllabus=[VECTOR, FLIGHT])

    after_dpm = DPMProfile(
        student_id=student_id,
        persona=PERSONA,
        weaknesses={
            FLIGHT: Weakness(mastery="known", strength="strong",
                             evidence=[f"{FIRST}#5"]),
            VECTOR: Weakness(mastery="misconceived", strength="weak",
                             evidence=[f"{FIRST}#2"]),
        },
    )
    after_tm = TeachingMemory(
        student_id=student_id,
        syllabus=[VECTOR, FLIGHT],
        covered={
            FLIGHT: CoveredConcept(elements_used=["recall"],
                                   taught_at=[f"{FIRST}#4"], status="covered"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id=VECTOR,
                doubt=(
                    "Asked for the horizontal component of the launch "
                    "velocity, he answered 'u sin theta' — the vertical one. "
                    "Swaps sin and cos under pressure rather than not knowing "
                    "them."
                ),
                correct_understanding=(
                    "Horizontal is u cos(theta) because the angle is measured "
                    "from the ground, so the adjacent side is the horizontal "
                    "one. Anchoring it to the triangle rather than to the "
                    "letters is what makes it stick."
                ),
                status="active",
                evidence=[f"{FIRST}#2"],
            ),
        ],
        teaching_style=TeachingStyle(current_mode="direct"),
    )

    log = SessionLog(
        session_id=FIRST,
        student_id=student_id,
        started_at=when,
        ended_at=when + timedelta(minutes=14),
        topic="Projectile motion — components",
        mode="revision",
        summary=(
            "First look at resolving the launch velocity. Recalled the time of "
            "flight formula unprompted and confidently, but gave u sin(theta) "
            "for the HORIZONTAL component — the vertical one. Corrected in the "
            "moment, not yet re-checked."
        ),
        turns=[
            Turn(turn=1, role="tutor",
                 text="What is the horizontal velocity of a projectile?",
                 concept_id=VECTOR),
            Turn(turn=2, role="student", text="u sin theta", concept_id=VECTOR),
            Turn(turn=3, role="tutor",
                 text="Close — that is the vertical one. Horizontally it is u cos theta.",
                 concept_id=VECTOR),
            Turn(turn=4, role="tutor",
                 text="Do you remember the time of flight?", concept_id=FLIGHT),
            Turn(turn=5, role="student",
                 text="Time of flight formula 2u sin theta / g.", concept_id=FLIGHT),
        ],
        dpm_before=before_dpm, dpm_after=after_dpm,
        teaching_before=before_tm, teaching_after=after_tm,
        operations=[
            {"op": "set_mastery", "concept_id": FLIGHT,
             "args": {"mastery": "known", "strength": "strong"}, "applied": True},
            {"op": "set_mastery", "concept_id": VECTOR,
             "args": {"mastery": "misconceived", "strength": "weak"}, "applied": True},
            {"op": "open_doubt", "concept_id": VECTOR, "args": {}, "applied": True},
            # The validation gate visibly refusing something. This is the more
            # convincing half of the demonstration: a memory layer where every
            # proposed write succeeds is indistinguishable from one with no
            # rules at all. close_doubt on the same session it was opened in is
            # exactly what app/memory/ops.py now rejects.
            {"op": "close_doubt", "concept_id": VECTOR,
             "args": {"note": "one correct answer in the same session is not a re-check"},
             "applied": False},
        ],
    )
    return log, after_dpm, after_tm


def _second_session(
    student_id: str, when: datetime, dpm_before: DPMProfile, tm_before: TeachingMemory
) -> tuple[SessionLog, DPMProfile, TeachingMemory]:
    """Two days ago, picking up from the first. Movement in both directions:
    one concept improves, one new weakness appears."""
    after_dpm = DPMProfile(
        student_id=student_id,
        persona=PERSONA,
        weaknesses={
            FLIGHT: Weakness(mastery="known", strength="strong",
                             evidence=[f"{FIRST}#5"]),
            # Moved: he got there, but needed walking through every step.
            VECTOR: Weakness(mastery="partial", strength="weak",
                             evidence=[f"{FIRST}#2", f"{SECOND}#4"]),
            MOTION: Weakness(mastery="partial", strength="weak",
                             evidence=[f"{SECOND}#6"]),
            HEIGHT: Weakness(mastery="unknown", strength="weak",
                             evidence=[f"{SECOND}#1"]),
        },
    )
    after_tm = TeachingMemory(
        student_id=student_id,
        syllabus=[VECTOR, FLIGHT, MOTION, HEIGHT],
        covered={
            FLIGHT: CoveredConcept(elements_used=["recall"],
                                   taught_at=[f"{FIRST}#4"], status="covered"),
            MOTION: CoveredConcept(elements_used=["guided-derivation"],
                                   taught_at=[f"{SECOND}#3"], status="in_progress"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id=VECTOR,
                doubt=(
                    "Still reaches for sine when asked for the horizontal "
                    "component, though he self-corrects when prompted to look "
                    "at the triangle."
                ),
                correct_understanding=(
                    "Horizontal is u cos(theta): the angle sits on the ground, "
                    "so the horizontal side is the adjacent one."
                ),
                status="active",
                evidence=[f"{FIRST}#2", f"{SECOND}#4"],
            ),
            OpenDoubt(
                concept_id=MOTION,
                doubt=(
                    "Can derive R = u^2 sin(2 theta)/g when walked through it, "
                    "but has not said WHY 45 degrees maximises it."
                ),
                correct_understanding=(
                    "sin(2 theta) is largest at 1, which needs 2 theta = 90, so "
                    "theta = 45. The angle is the only free variable once u and "
                    "g are fixed."
                ),
                status="active",
                evidence=[f"{SECOND}#6"],
            ),
        ],
        # He was led to the answer step by step and got there, so that is what
        # has been working.
        teaching_style=TeachingStyle(
            current_mode="socratic",
            notes=[f"Responds well to being asked rather than told ({SECOND})."],
        ),
    )

    log = SessionLog(
        session_id=SECOND,
        student_id=student_id,
        started_at=when,
        ended_at=when + timedelta(minutes=17),
        topic="Maximum range",
        mode="revision",
        summary=(
            "Derived the range formula from time of flight with prompting and "
            "reached sin(2 theta) himself. The sin/cos swap surfaced again "
            "under pressure but he corrected it once pointed at the triangle. "
            "Stopped before explaining why 45 degrees is the maximum."
        ),
        turns=[
            Turn(turn=1, role="tutor",
                 text="Tonight: what makes the range as large as it can be?",
                 concept_id=HEIGHT),
            Turn(turn=2, role="tutor",
                 text="Start from time of flight — you had that one.",
                 concept_id=FLIGHT),
            Turn(turn=3, role="student",
                 text="u cos theta times 2 u sin theta over g.", concept_id=MOTION),
            Turn(turn=4, role="student",
                 text="wait, horizontal is cos — I said sin again.", concept_id=VECTOR),
            Turn(turn=5, role="tutor",
                 text="Which identity equals 2 sin theta cos theta?",
                 concept_id=MOTION),
            Turn(turn=6, role="student", text="sin 2 theta", concept_id=MOTION),
        ],
        dpm_before=dpm_before, dpm_after=after_dpm,
        teaching_before=tm_before, teaching_after=after_tm,
        operations=[
            # The movement the recap screen exists to show.
            {"op": "set_mastery", "concept_id": VECTOR,
             "args": {"mastery": "partial", "strength": "weak"}, "applied": True},
            {"op": "set_mastery", "concept_id": MOTION,
             "args": {"mastery": "partial", "strength": "weak"}, "applied": True},
            {"op": "set_mastery", "concept_id": HEIGHT,
             "args": {"mastery": "unknown", "strength": "weak"}, "applied": True},
            {"op": "open_doubt", "concept_id": MOTION, "args": {}, "applied": True},
            {"op": "update_coverage", "concept_id": MOTION,
             "args": {"status": "in_progress"}, "applied": True},
            # Refused: an out-of-enum mastery value. apply_operations drops the
            # whole operation rather than writing a half-valid record.
            {"op": "set_mastery", "concept_id": FLIGHT,
             "args": {"mastery": "mastered", "note": "not a valid mastery level"},
             "applied": False},
        ],
    )
    return log, after_dpm, after_tm


def wipe(conn, student_id: str) -> int:
    """Back to nothing: no sessions, empty record."""
    gone = store.delete_session_logs(conn, student_id)
    store.put_dpm(conn, DPMProfile(student_id=student_id))
    store.put_teaching_memory(conn, TeachingMemory(student_id=student_id))
    return gone


def seed(conn, student_id: str) -> None:
    now = datetime.now(timezone.utc)

    first, dpm, tm = _first_session(student_id, now - timedelta(days=4))
    store.put_session_log(conn, first)

    second, dpm, tm = _second_session(
        student_id, now - timedelta(days=2), dpm, tm)
    store.put_session_log(conn, second)

    # The live record is the second session's after-state, exactly as it would
    # be if these two had really just run.
    store.put_dpm(conn, dpm)
    store.put_teaching_memory(conn, tm)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--student", default=DEFAULT_STUDENT, help="Firebase uid")
    ap.add_argument("--email", default=DEFAULT_EMAIL, help="only for the printout")
    ap.add_argument("--clear", action="store_true", help="wipe and stop")
    args = ap.parse_args()

    conn = store.connect()
    print(f"store: {store.backend()}")

    gone = wipe(conn, args.student)
    print(f"cleared {gone} session log(s) and the record for {args.student}")
    if args.clear:
        return 0

    seed(conn, args.student)

    logs = store.list_session_logs(conn, args.student)
    dpm = store.get_dpm(conn, args.student)
    tm = store.get_teaching_memory(conn, args.student)
    print(f"\nseeded {args.email}")
    print(f"  sessions      : {len(logs)}")
    for entry in logs:
        moved = sum(
            1 for cid in set(entry.dpm_before.weaknesses if entry.dpm_before else {})
            | set(entry.dpm_after.weaknesses if entry.dpm_after else {})
            if (entry.dpm_before.weaknesses.get(cid) if entry.dpm_before else None)
            != (entry.dpm_after.weaknesses.get(cid) if entry.dpm_after else None)
        )
        refused = sum(1 for o in entry.operations if not o.get("applied"))
        print(f"      {entry.session_id}  {entry.topic:34} "
              f"{moved} change(s), {refused} refused")
    print(f"  weaknesses    : {len(dpm.weaknesses)}")
    for cid, w in dpm.weaknesses.items():
        print(f"      {w.mastery:12} {w.strength:6} {cid}")
    print(f"  open doubts   : {len(tm.open_doubts)}")
    print(f"  mode          : {tm.teaching_style.current_mode}")
    print(f"  interests     : {', '.join(dpm.persona.interests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
