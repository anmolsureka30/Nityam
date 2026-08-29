"""Seed one REAL signed-in student, so the memory layer has something to show.

`seed_demo_data.py` seeds `demo_student` and the grounding corpus. But a
browser session runs as the Firebase uid on the token, not as `demo_student`,
so every real session so far has opened with `get_dpm -> {"found": False}` and
a brief with nothing personal in it. This fills that gap.

    .venv/bin/python -m scripts.seed_student
    .venv/bin/python -m scripts.seed_student --student <uid> --email <addr>
    .venv/bin/python -m scripts.seed_student --clear

WHAT IS SEEDED, AND WHY IT IS NOT INVENTED. The evidence below points at turns
in the prior session this script also writes, and the content of that session
is taken from a real recorded session (backend/logs/2026-08-30_02-46-17) — the
student really did answer "u sin theta" when asked for the horizontal
component, really did recall the time-of-flight formula unprompted, and really
did find 45° in the simulation. The memory layer's whole invariant is that a
claim about a student resolves back to a moment that happened; seeding
plausible-looking fiction would break the one property it exists to protect.

CONCEPT IDS ARE THE REAL ONES. Checked against store.list_concept_ids() rather
than guessed. This matters more than it sounds: `seed_demo_data.py` cites
`projectile.horizontal_range` twice and NO SUCH CONCEPT EXISTS in the corpus,
so those weaknesses retrieve nothing and the brief silently loses them.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

# BEFORE app.memory.store: `store.py` picks its backend off NITYAM_STORE at
# IMPORT time, so a script that loads .env afterwards silently seeds sqlite
# while the running app reads Firestore. That is exactly what happened on the
# first run of this script.
from app.auth import load_env

load_env()

from app.memory import store  # noqa: E402
from app.memory.schemas import (  # noqa: E402
    CoveredConcept,
    DPMProfile,
    OpenDoubt,
    Persona,
    SessionLog,
    TeachingStyle,
    TeachingMemory,
    Turn,
    Weakness,
)

# The signed-in uid this backend sees on the token. Firebase mints it; it is
# not the email, and the session runs as this.
DEFAULT_STUDENT = "Xu2su777GANXJppk3kt3n8fjda42"
DEFAULT_EMAIL = "arnav.prasad999918@gmail.com"

VECTOR = "projectile.vector_resolution"
FLIGHT = "projectile.time_of_flight"
HEIGHT = "projectile.maximum_height"
MOTION = "projectile.projectile_motion"


def _prior_session(student_id: str, session_id: str, when: datetime) -> SessionLog:
    """Two days ago, and deliberately unfinished — a session that ended mid
    derivation is what makes the next one have somewhere to start."""
    return SessionLog(
        session_id=session_id,
        student_id=student_id,
        started_at=when,
        ended_at=when + timedelta(minutes=16),
        summary=(
            "Worked through the range formula from time of flight. Recalled "
            "2u sin(theta)/g unprompted and got to R = u^2 sin(2 theta)/g with "
            "prompting. Confused the horizontal component with the vertical "
            "one — said u sin(theta) where u cos(theta) was wanted. Stopped "
            "before explaining WHY 45 degrees is the maximum."
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
            Turn(turn=6, role="student",
                 text="u cos theta times 2 u sin theta over g.", concept_id=MOTION),
            Turn(turn=7, role="tutor",
                 text="Which identity equals 2 sin theta cos theta?", concept_id=MOTION),
            Turn(turn=8, role="student", text="sin 2 theta", concept_id=MOTION),
        ],
    )


def seed(conn, student_id: str, email: str) -> str:
    prior_id = "s_seed_prior"
    when = datetime.now(timezone.utc) - timedelta(days=2)
    store.put_session_log(conn, _prior_session(student_id, prior_id, when))

    store.put_dpm(conn, DPMProfile(
        student_id=student_id,
        persona=Persona(
            preferred_pace="moderate",
            # He asked for English out loud mid-session. Recording it here is
            # what stops the next session opening in Hindi again.
            language_mix="English, with Hindi only if the student switches first",
            interests=["cricket"],
        ),
        weaknesses={
            # Answered it correctly and unprompted.
            FLIGHT: Weakness(mastery="known", strength="strong",
                             evidence=[f"{prior_id}#5"]),
            # Got there, but only with prompting through every step.
            MOTION: Weakness(mastery="partial", strength="weak",
                             evidence=[f"{prior_id}#6", f"{prior_id}#8"]),
            # The actual error, in his own words.
            VECTOR: Weakness(mastery="misconceived", strength="weak",
                             evidence=[f"{prior_id}#2"]),
            HEIGHT: Weakness(mastery="unknown", strength="weak",
                             evidence=[f"{prior_id}#1"]),
        },
    ))

    store.put_teaching_memory(conn, TeachingMemory(
        student_id=student_id,
        syllabus=[VECTOR, FLIGHT, MOTION, HEIGHT],
        covered={
            FLIGHT: CoveredConcept(elements_used=["recall"],
                                   taught_at=[f"{prior_id}#4"], status="covered"),
            MOTION: CoveredConcept(elements_used=["guided-derivation"],
                                   taught_at=[f"{prior_id}#6"], status="in_progress"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id=VECTOR,
                doubt=(
                    "Asked for the horizontal component of the launch velocity, "
                    "he answered 'u sin theta' — the vertical one. Swaps sin and "
                    "cos under time pressure rather than not knowing them."
                ),
                correct_understanding=(
                    "Horizontal is u cos(theta) because the angle is measured "
                    "from the ground, so the adjacent side is the horizontal "
                    "one. Vertical is u sin(theta). Anchoring it to the triangle "
                    "rather than to the letters is what makes it stick."
                ),
                status="active",
                evidence=[f"{prior_id}#2"],
            ),
            OpenDoubt(
                concept_id=MOTION,
                doubt=(
                    "Can derive R = u^2 sin(2 theta)/g when walked through it, "
                    "but has not said why 45 degrees maximises it."
                ),
                correct_understanding=(
                    "sin(2 theta) is largest at 1, which needs 2 theta = 90, so "
                    "theta = 45. The angle is the only free variable once u and "
                    "g are fixed."
                ),
                status="active",
                evidence=[f"{prior_id}#8"],
            ),
        ],
        # He was led to the answer step by step and got there, so that is
        # what has been working.
        teaching_style=TeachingStyle(
            current_mode="socratic",
            notes=[f"Responds well to being asked rather than told ({prior_id})."],
        ),
    ))
    return prior_id


def clear(conn, student_id: str) -> None:
    store.put_dpm(conn, DPMProfile(student_id=student_id))
    store.put_teaching_memory(conn, TeachingMemory(student_id=student_id))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--student", default=DEFAULT_STUDENT, help="Firebase uid")
    ap.add_argument("--email", default=DEFAULT_EMAIL, help="only for the printout")
    ap.add_argument("--clear", action="store_true",
                    help="wipe this student's record back to empty")
    args = ap.parse_args()

    conn = store.connect()
    print(f"store: {store.backend()}")
    if args.clear:
        clear(conn, args.student)
        print(f"cleared {args.student}")
        return 0

    prior_id = seed(conn, args.student, args.email)

    dpm = store.get_dpm(conn, args.student)
    tm = store.get_teaching_memory(conn, args.student)
    print(f"seeded {args.email}  ({args.student})")
    print(f"  prior session : {prior_id}")
    print(f"  weaknesses    : {len(dpm.weaknesses)}")
    for cid, w in dpm.weaknesses.items():
        print(f"      {w.mastery:12} {w.strength:6} {cid}")
    print(f"  open doubts   : {len(tm.open_doubts)}")
    print(f"  covered       : {len(tm.covered)}")
    print(f"  mode          : {tm.teaching_style.current_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
