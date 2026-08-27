"""One-off demo script: a genuinely rich scenario. Seeds a plausible PRIOR
long-term memory (as if from an earlier session_0), then drives a real
multi-turn session_1 through the real memory pipeline, then closes it for
real (real Gemini reflect() call, not stubbed) -- so Working, Episodic, and
Long-Term memory all end up populated with real, non-trivial content, and
the long-term diff reflects a genuine LLM judgment, not a scripted one.
Not part of the plan/tests -- deleted after the demo.
"""
import asyncio
from unittest.mock import MagicMock

import httpx

from app.memory import store
from app.memory.schemas import (
    CoveredConcept,
    DPMProfile,
    OpenDoubt,
    Persona,
    SelfReflection,
    TeachingMemory,
    TeachingStyle,
    Weakness,
)

STUDENT_ID = "demo_student"
SESSION_ID = "demo_rich_session_1"
TUTOR_URL = "http://127.0.0.1:8010"


def seed_baseline():
    conn = store.connect()
    store.put_dpm(conn, DPMProfile(
        student_id=STUDENT_ID,
        persona=Persona(preferred_pace="moderate", interests=["pirates", "sports"]),
        weaknesses={
            "projectile.range": Weakness(mastery="partial", strength="weak", evidence=["session_0#3"]),
            "projectile.time_of_flight": Weakness(mastery="known", strength="strong", evidence=["session_0#6"]),
        },
        self_reflection=[
            SelfReflection(note="Engages well with pirate/adventure-themed examples", evidence=["session_0#2"], status="active"),
        ],
    ))
    store.put_teaching_memory(conn, TeachingMemory(
        student_id=STUDENT_ID,
        syllabus=["projectile.range", "projectile.time_of_flight", "projectile.max_height", "projectile.horizontal_velocity"],
        covered={
            "projectile.time_of_flight": CoveredConcept(elements_used=["worked-example"], taught_at=["session_0"], status="covered"),
        },
        open_doubts=[
            OpenDoubt(
                concept_id="projectile.range",
                doubt="Thinks a heavier cannonball travels farther than a lighter one fired the same way",
                correct_understanding="Range depends only on launch speed and angle, not mass, when air resistance is ignored",
                status="active",
                evidence=["session_0#4"],
            ),
        ],
        teaching_style=TeachingStyle(current_mode="socratic"),
    ))
    print("baseline seeded: 2 weaknesses, 1 self-reflection, 1 covered concept, 1 open doubt")


TURNS = [
    ("student", "Last time we talked about how a cannonball's mass doesn't affect how far it goes, right? I've been thinking about it and I think I finally get why: gravity pulls every mass down at the same rate, so a heavier ball doesn't fall any differently -- it's really just the launch speed and angle that matter, not the weight.", "projectile.range"),
    ("tutor", "Exactly right! You've nailed it. Mass genuinely doesn't affect the trajectory shape at all, once we ignore air resistance. Nice, clean reasoning. Let's build on that -- what do you think determines the *maximum height* a projectile reaches?", "projectile.max_height"),
    ("student", "Is it related to the vertical part of the velocity? Like, the faster it's moving upward at launch, the higher it'll climb before gravity slows it to a stop?", "projectile.max_height"),
    ("tutor", "Precisely! Maximum height only depends on the vertical component of the initial velocity -- u times sine of the launch angle. The horizontal component has zero effect on how high it goes.", "projectile.max_height"),
    ("student", "So if two cannons fire at the same speed but different angles, the one closer to 90 degrees goes higher, but the one closer to 45 probably goes farther overall?", "projectile.max_height"),
    ("tutor", "Exactly -- you're now connecting maximum height and range as a real trade-off. That's precisely the kind of thing a pirate gunner would have to weigh when aiming a cannon at a distant ship versus a nearby one.", "projectile.trajectory"),
]


async def drive_session():
    from app.memory import tools

    ctx = MagicMock()
    ctx.state = {"student_id": STUDENT_ID}
    ctx.session.id = SESSION_ID

    for role, text, concept_id in TURNS:
        await tools.log_turn(text, role, concept_id, "", ctx)
        print(f"logged turn [{role}] ({concept_id})")
        await asyncio.sleep(1.2)


def close_for_real():
    resp = httpx.post(
        f"{TUTOR_URL}/memory/sessions/{SESSION_ID}/close",
        json={"student_id": STUDENT_ID},
        timeout=60.0,
    )
    resp.raise_for_status()
    print("close_session response:", resp.json()["summary"] or "(no summary text)")


async def main():
    seed_baseline()
    await drive_session()
    print("closing session for real (live Gemini reflect() call)...")
    close_for_real()
    print("session_id:", SESSION_ID)


if __name__ == "__main__":
    asyncio.run(main())
