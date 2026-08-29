"""The starting record a demo student has, and the only definition of it.

Used by two callers that must not drift apart: `scripts/seed_student.py` (the
CLI you run before a demo) and the reset endpoint the account menu calls. It
lived in the script, which meant the button and the command could have seeded
different things.

THE TWO SESSIONS ARE THE PREREQUISITES FOR TONIGHT, not a rehearsal of it.
Mr. Deshpande derived the range formula in class on Tue 25 Aug and asked "Why
is 45 degrees special? Think about it tonight" — and never answered it
(frontend lib/data.ts:classRecap). Tonight's session is that question, so the
record behind it is what a student would already have covered on the way there:

    5 days ago   Resolving a vector into components
    2 days ago   Motion in two dimensions — the two axes are independent
    TONIGHT      Maximum range, and why 45 degrees wins   <- never seeded

Seeding tonight's topic as a past session would make the live session look like
a repeat, which is the opposite of the point.

WHY THE CONTENT IS NOT INVENTED. The failures come from real recorded sessions
(backend/logs/2026-08-30_02-46-17 and 03-37-59): he really did answer "u sin
theta" when asked for the horizontal component, and really did need walking
through the derivation. Every evidence pointer resolves to a turn in one of the
logs written here, about the concept it is cited for — the memory layer's one
invariant is that a claim about a student traces back to a moment that
happened, and a seed that broke it would be worse than no seed.

CONCEPT IDS ARE THE REAL ONES, checked against store.list_concept_ids().
`scripts/seed_demo_data.py` cites `projectile.horizontal_range` twice and no
such concept exists in the corpus, so those weaknesses retrieve nothing and
vanish from the brief with no error at all.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.memory import store
from app.memory.schemas import (
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


def reset(conn, student_id: str) -> dict:
    """Wipe this student and lay the starting record back down. Idempotent.

    The one entry point. Both the CLI and the account menu's "Reset my
    account" call this, so the button and the command cannot seed different
    things — which they could when this logic lived only in the script.
    """
    cleared = wipe(conn, student_id)
    seed(conn, student_id)
    return {"cleared_sessions": cleared, "seeded_sessions": 2}


def has_record(conn, student_id: str) -> bool:
    """Whether this student has ever been seen. Used to decide whether a new
    sign-in should be given the starting record."""
    try:
        profile = store.get_dpm(conn, student_id)
    except Exception:  # noqa: BLE001 - an unreachable store is not "new"
        return True
    return profile is not None and bool(profile.weaknesses)
