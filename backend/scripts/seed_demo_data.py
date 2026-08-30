"""Seed one demo student against real, already-ingested projectile-motion
content from sub_modules_examples/shruti/vault/wiki/ — not invented text
(architecture.md, "Demo subject" decision).

Run directly: `.venv/bin/python -m scripts.seed_demo_data`
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.memory import store
from app.memory.schemas import (
    CoveredConcept,
    DPMProfile,
    OpenDoubt,
    Persona,
    SessionLog,
    TeachingMemory,
    Turn,
    Weakness,
)
from app.memory.shruti_sync import parse_wiki_file

# backend/scripts/ -> backend/ -> repo root. (This file moved up one level
# when it came out of sub_modules_examples/tutor/, so the walk is 3, not 4.)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = REPO_ROOT / "sub_modules_examples" / "shruti" / "vault" / "wiki"


def seed(conn) -> None:
    concept_ids = []
    for wiki_file in sorted(WIKI_DIR.glob("*.md")):
        chunks = parse_wiki_file(wiki_file)
        for chunk in chunks:
            store.put_grounding_chunk(conn, chunk)
        if chunks:
            concept_ids.append(chunks[0].concept_ids[0])

    # STUB: a hand-written prior session, so the tutor has something to know
    # about this student on turn one. In the real product session_close.py
    # writes this after every session and Shruti supplies the lecture side.
    #
    # The evidence citations below point at real turns in the session log
    # seeded with them, not at invented ones — the memory layer's whole
    # invariant is that every claim resolves back to a moment that happened
    # (memory_layer.md §2-§3), and seeding fake references would quietly break
    # the one property the design exists to protect.
    prior_id = "s_prev_0"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    store.put_session_log(conn, SessionLog(
        session_id=prior_id,
        student_id="demo_student",
        started_at=yesterday,
        ended_at=yesterday + timedelta(minutes=18),
        summary=(
            "First look at projectile motion. Comfortable resolving a velocity "
            "into components; kept reaching for speed rather than angle when "
            "asked what changes the range."
        ),
        turns=[
            Turn(turn=1, role="tutor", text="Break the launch velocity into its two parts for me.",
                 concept_id="projectile.vector_resolution"),
            Turn(turn=2, role="student", text="u cos theta along the ground and u sin theta upward.",
                 concept_id="projectile.vector_resolution"),
            Turn(turn=3, role="tutor", text="So if you wanted it to land further, what would you change?",
                 concept_id="projectile.horizontal_range"),
            Turn(turn=4, role="student", text="Throw it harder — more speed means more distance.",
                 concept_id="projectile.horizontal_range"),
        ],
    ))

    store.put_dpm(conn, DPMProfile(
        student_id="demo_student",
        persona=Persona(preferred_pace="moderate", language_mix="en", interests=["cricket"]),
        weaknesses={
            "projectile.vector_resolution": Weakness(
                mastery="known", strength="strong", evidence=[f"{prior_id}#2"],
            ),
            "projectile.horizontal_range": Weakness(
                mastery="misconceived", strength="weak", evidence=[f"{prior_id}#4"],
            ),
        },
    ))
    store.put_teaching_memory(conn, TeachingMemory(
        student_id="demo_student",
        syllabus=concept_ids,
        covered={
            "projectile.vector_resolution": CoveredConcept(
                elements_used=["worked-example"], taught_at=[f"{prior_id}#1"], status="covered",
            ),
        },
        open_doubts=[
            OpenDoubt(
                concept_id="projectile.horizontal_range",
                doubt="Thinks range is decided by how hard you throw, so reaches for speed before angle.",
                correct_understanding=(
                    "With u and g fixed, range depends on sin(2θ), so the angle is "
                    "the only thing under their control — and it peaks at 45°."
                ),
                status="active",
                evidence=[f"{prior_id}#4"],
            ),
        ],
    ))


if __name__ == "__main__":
    conn = store.connect()
    seed(conn)
    print(f"Seeded demo_student against {WIKI_DIR}")
