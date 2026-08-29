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

THE TWO SESSIONS ARE THE PREREQUISITES FOR TONIGHT, not a rehearsal of it.
Mr. Deshpande derived the range formula in class on Tue 25 Aug and asked "Why
is 45 degrees special? Think about it tonight" — and never answered it
(lib/data.ts:classRecap). Tonight's session is that question. So the record
behind it has to be what a student would already have covered on the way
there:

    5 days ago   Resolving a vector into components
    2 days ago   Motion in two dimensions — the two axes are independent
    TONIGHT      Maximum range, and why 45 degrees wins   <- not seeded

Seeding tonight's topic as a past session would make the live session look
like a repeat, which is the opposite of the point.

WHY THE CONTENT IS NOT INVENTED. The failures are taken from real recorded
sessions (backend/logs/2026-08-30_02-46-17 and 03-37-59): the student really
did answer "u sin theta" when asked for the horizontal component, and really
did need walking through every step of the derivation. The memory layer's
invariant is that a claim about a student resolves back to a moment that
happened.

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
    """Five days ago. Vectors, before any of this was about projectiles.

    The first thing the chapter needs, and the first thing he got wrong. Only
    ONE concept moves here — every evidence pointer below resolves to a turn in
    this log that is actually about that concept, which is the property the
    whole memory layer rests on.
    """
    before_dpm = DPMProfile(student_id=student_id, persona=PERSONA)
    before_tm = TeachingMemory(student_id=student_id, syllabus=[VECTOR])

    after_dpm = DPMProfile(
        student_id=student_id,
        persona=PERSONA,
        weaknesses={
            VECTOR: Weakness(mastery="misconceived", strength="weak",
                             evidence=[f"{FIRST}#2"]),
        },
    )
    after_tm = TeachingMemory(
        student_id=student_id,
        syllabus=[VECTOR],
        covered={
            VECTOR: CoveredConcept(elements_used=["worked-example"],
                                   taught_at=[f"{FIRST}#1"], status="in_progress"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id=VECTOR,
                doubt=(
                    "Asked for the horizontal component of a launch velocity, "
                    "he answered 'u sin theta' — the vertical one. Swaps sin "
                    "and cos under pressure rather than not knowing them."
                ),
                correct_understanding=(
                    "Horizontal is u cos(theta) because the angle is measured "
                    "from the ground, so the horizontal side is the adjacent "
                    "one. Anchoring it to the triangle rather than to the "
                    "letters is what makes it stick."
                ),
                status="active",
                evidence=[f"{FIRST}#2"],
            ),
        ],
        teaching_style=TeachingStyle(current_mode="worked-example"),
    )

    log = SessionLog(
        session_id=FIRST,
        student_id=student_id,
        started_at=when,
        ended_at=when + timedelta(minutes=14),
        topic="Resolving a vector into components",
        mode="revision",
        summary=(
            "Broke a velocity into its horizontal and vertical parts for the "
            "first time. Comfortable with the triangle itself, but gave "
            "u sin(theta) for the HORIZONTAL component — that is the vertical "
            "one. Self-corrected once pointed at the triangle, so it is a swap "
            "under pressure rather than a gap. Not yet re-checked."
        ),
        turns=[
            Turn(turn=1, role="tutor",
                 text="If you throw a ball at an angle, what are its two "
                      "velocity components?", concept_id=VECTOR),
            Turn(turn=2, role="student", text="u sin theta along the ground.",
                 concept_id=VECTOR),
            Turn(turn=3, role="tutor",
                 text="That is the vertical one. Draw the triangle — the angle "
                      "sits on the ground.", concept_id=VECTOR),
            Turn(turn=4, role="student",
                 text="oh, the horizontal is the one next to it. So cos.",
                 concept_id=VECTOR),
            Turn(turn=5, role="tutor",
                 text="Exactly. Adjacent is cosine. We will come back to this.",
                 concept_id=VECTOR),
        ],
        dpm_before=before_dpm, dpm_after=after_dpm,
        teaching_before=before_tm, teaching_after=after_tm,
        operations=[
            {"op": "set_mastery", "concept_id": VECTOR,
             "args": {"mastery": "misconceived", "strength": "weak"}, "applied": True},
            {"op": "open_doubt", "concept_id": VECTOR, "args": {}, "applied": True},
            {"op": "update_coverage", "concept_id": VECTOR,
             "args": {"status": "in_progress"}, "applied": True},
            # The validation gate visibly refusing something, and this is the
            # more convincing half of the demonstration: a memory layer where
            # every proposed write succeeds is indistinguishable from one with
            # no rules at all. Closing a doubt in the same session it was
            # opened is exactly what app/memory/ops.close_doubt now rejects —
            # one correct answer ten minutes later is not a spaced re-check.
            {"op": "close_doubt", "concept_id": VECTOR,
             "args": {"why_refused": "he corrected it in the same session; "
                                     "that is not a re-check"},
             "applied": False},
        ],
    )
    return log, after_dpm, after_tm


def _second_session(
    student_id: str, when: datetime, dpm_before: DPMProfile, tm_before: TeachingMemory
) -> tuple[SessionLog, DPMProfile, TeachingMemory]:
    """Two days ago. The two axes are independent — the idea the whole of
    tonight rests on, and the last thing before Mr. Deshpande's question.

    Movement in both directions, which is what makes a record look like a
    record: the sin/cos swap improves, and two new concepts arrive weak.
    """
    after_dpm = DPMProfile(
        student_id=student_id,
        persona=PERSONA,
        weaknesses={
            # Improved, but not resolved: he still reaches for sine first.
            VECTOR: Weakness(mastery="partial", strength="weak",
                             evidence=[f"{FIRST}#2", f"{SECOND}#5"]),
            FLIGHT: Weakness(mastery="known", strength="strong",
                             evidence=[f"{SECOND}#3"]),
            MOTION: Weakness(mastery="partial", strength="weak",
                             evidence=[f"{SECOND}#7"]),
        },
    )
    after_tm = TeachingMemory(
        student_id=student_id,
        syllabus=[VECTOR, FLIGHT, MOTION],
        covered={
            VECTOR: CoveredConcept(elements_used=["worked-example", "re-check"],
                                   taught_at=[f"{FIRST}#1", f"{SECOND}#4"],
                                   status="in_progress"),
            FLIGHT: CoveredConcept(elements_used=["recall"],
                                   taught_at=[f"{SECOND}#2"], status="covered"),
            MOTION: CoveredConcept(elements_used=["guided-derivation"],
                                   taught_at=[f"{SECOND}#6"], status="in_progress"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id=VECTOR,
                doubt=(
                    "Still says sine first when asked for the horizontal "
                    "component, though he now catches it himself when told to "
                    "look at the triangle."
                ),
                correct_understanding=(
                    "Horizontal is u cos(theta): the angle sits on the ground, "
                    "so the horizontal side is the adjacent one."
                ),
                status="active",
                evidence=[f"{FIRST}#2", f"{SECOND}#5"],
            ),
            OpenDoubt(
                concept_id=MOTION,
                doubt=(
                    "Treats the horizontal and vertical motions as one coupled "
                    "problem — expects the horizontal speed to drop as the ball "
                    "climbs."
                ),
                correct_understanding=(
                    "The two axes are independent. Gravity acts only "
                    "vertically, so the horizontal speed never changes; the "
                    "vertical one slows, stops and reverses. That independence "
                    "is what makes the range come apart into u cos(theta) "
                    "times the time of flight."
                ),
                status="active",
                evidence=[f"{SECOND}#7"],
            ),
        ],
        # He was led to it step by step and got there, so that is what works.
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
        topic="Motion in two dimensions",
        mode="revision",
        summary=(
            "Time of flight landed cleanly — recalled 2u sin(theta)/g "
            "unprompted. The sin/cos swap resurfaced but he caught it himself "
            "this time. Still expects the horizontal speed to fall off as the "
            "ball rises, so the independence of the two axes has not landed "
            "yet — which is the idea the range formula is built on."
        ),
        turns=[
            Turn(turn=1, role="tutor",
                 text="Today: the two directions do not talk to each other.",
                 concept_id=MOTION),
            Turn(turn=2, role="tutor",
                 text="How long is the ball in the air?", concept_id=FLIGHT),
            Turn(turn=3, role="student", text="2 u sin theta over g.",
                 concept_id=FLIGHT),
            Turn(turn=4, role="tutor",
                 text="And how far does it travel sideways in that time?",
                 concept_id=VECTOR),
            Turn(turn=5, role="student",
                 text="u sin theta times — no wait, cos. u cos theta.",
                 concept_id=VECTOR),
            Turn(turn=6, role="tutor",
                 text="Good catch. Does that horizontal speed change on the "
                      "way up?", concept_id=MOTION),
            Turn(turn=7, role="student",
                 text="it should slow down a bit as it goes higher, right?",
                 concept_id=MOTION),
        ],
        dpm_before=dpm_before, dpm_after=after_dpm,
        teaching_before=tm_before, teaching_after=after_tm,
        operations=[
            {"op": "set_mastery", "concept_id": VECTOR,
             "args": {"mastery": "partial", "strength": "weak"}, "applied": True},
            {"op": "set_mastery", "concept_id": FLIGHT,
             "args": {"mastery": "known", "strength": "strong"}, "applied": True},
            {"op": "set_mastery", "concept_id": MOTION,
             "args": {"mastery": "partial", "strength": "weak"}, "applied": True},
            {"op": "open_doubt", "concept_id": MOTION, "args": {}, "applied": True},
            {"op": "update_coverage", "concept_id": FLIGHT,
             "args": {"status": "covered"}, "applied": True},
            # Refused: "mastered" is not in the mastery enum, so
            # apply_operations drops the whole operation rather than writing a
            # half-valid record.
            {"op": "set_mastery", "concept_id": VECTOR,
             "args": {"mastery": "mastered",
                      "why_refused": "not one of the five allowed levels"},
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

    first, dpm, tm = _first_session(student_id, now - timedelta(days=5))
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
