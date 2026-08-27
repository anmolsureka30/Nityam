"""Five students, chosen to force specific memory-layer failure modes — see
docs/superpowers/specs/2026-08-27-memory-layer-eval-design.md §3.

Every concept_id used here has real, citable grounding_chunk content behind
it (confirmed against sub_modules_examples/shruti/vault/wiki/*.md's own
'## Taught in' sections before writing this file) — this eval is grounded in
real course content, not invented topics with nothing for search_grounding
to find.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Session:
    """One simulated session: a fixed sequence of student utterances. The
    tutor's replies are the real agent's live output — that's what's under
    test. Student turns are fixed so the transcript is reproducible across
    runs and graders have a stable basis for comparison."""

    label: str
    student_turns: list[str]


@dataclass
class Persona:
    student_id: str
    display_name: str
    preferred_pace: str  # "fast" | "moderate" | "deliberate"
    interests: list[str]
    sessions: list[Session]
    pre_seed: dict | None = field(default=None)
    """Only Rohan uses this: a DPMProfile/TeachingMemory written to Firestore
    BEFORE this eval's first live session, simulating a student who already
    has history from outside this eval run (not a live-session artifact)."""
    notes: str = ""


PERSONAS: list[Persona] = [
    Persona(
        student_id="eval_arjun",
        display_name="Arjun",
        preferred_pace="fast",
        interests=["cricket"],
        notes=(
            "Strong existing vector background, terse worked-examples. Tests "
            "whether the tutor SKIPS re-teaching basics a strong student "
            "doesn't need — the opposite failure from Priya."
        ),
        sessions=[
            Session(
                "session_1_range_and_time_of_flight",
                [
                    "Hey, can you explain horizontal range in projectile motion? I already get vectors pretty well.",
                    "Got it. And what about time of flight - is it just range divided by horizontal velocity?",
                    "Makes sense. Can we try a quick problem - a cricket ball hit at 30 m/s at 40 degrees, what's the range?",
                ],
            ),
            Session(
                "session_2_trajectory_equation",
                [
                    "Today let's do trajectory equations - I remember we did range and time of flight last time.",
                    "OK, and how does the impact angle come into this?",
                ],
            ),
            Session(
                "session_3_staircase_and_recheck",
                [
                    "Let's try that staircase projectile problem you mentioned before.",
                    "Wait, going back - for the trajectory equation, if a ball lands at a steep angle, does that change which formula I should use?",
                ],
            ),
        ],
    ),
    Persona(
        student_id="eval_priya",
        display_name="Priya",
        preferred_pace="deliberate",
        interests=["music"],
        notes=(
            "A real vector-resolution misconception (swaps sin/cos for "
            "components), socratic preference. Tests open_doubt lifecycle "
            "and the never-close-on-one-correct-answer rule."
        ),
        sessions=[
            Session(
                "session_1_vector_resolution_misconception",
                [
                    "Can we go slowly through vector resolution? I always get confused.",
                    "So for the horizontal component, would that be u sin(theta)? I think that's what I remember.",
                    "Oh okay. So then horizontal range - can we go through that step by step?",
                ],
            ),
            Session(
                "session_2_misconception_resurfaces",
                [
                    "Before we start max height, quick check - for a ball launched at 30 m/s at 60 degrees, what's the horizontal component again? Is it 30 sin(60)?",
                    "Okay that makes sense now. Let's do max height.",
                ],
            ),
            Session(
                "session_3_genuine_recheck",
                [
                    "Let's try a new one - velocity components being perpendicular. First, quick recap: horizontal component is u cos(theta), right?",
                    "Great, now explain the perpendicular condition.",
                ],
            ),
        ],
    ),
    Persona(
        student_id="eval_rohan",
        display_name="Rohan",
        preferred_pace="moderate",
        interests=["cricket", "video games"],
        notes=(
            "Pre-existing DPM/TeachingMemory, seeded before this eval's first "
            "live session - tests whether get_dpm/get_teaching_memory "
            "correctly load state that a prior LIVE session didn't create."
        ),
        pre_seed={
            "weaknesses": {
                "projectile.horizontal_range": {
                    "mastery": "known",
                    "strength": "strong",
                    "evidence": ["preseed#1"],
                }
            },
            "covered": {
                "projectile.horizontal_range": {
                    "elements_used": ["worked-example"],
                    "taught_at": ["preseed"],
                    "status": "covered",
                }
            },
        },
        sessions=[
            Session(
                "session_1_maximum_height_references_prior",
                [
                    "Hey I'm back - can we do maximum height today?",
                    "Cool, does this use similar logic to what we did with horizontal range?",
                ],
            ),
            Session(
                "session_2_adjacent_topic",
                [
                    "Random question - my friend was asking about rolling motion, like the velocity of the topmost point of a rolling ball. Is that related to what we've been doing?",
                ],
            ),
        ],
    ),
    Persona(
        student_id="eval_ananya",
        display_name="Ananya",
        preferred_pace="fast",
        interests=["painting", "art"],
        notes=(
            "Fast pace like Arjun (tests isolation between similar personas), "
            "visual-learner preference (tests ArtifactAgent delegation), works "
            "near-duplicate concept names (tests they aren't conflated)."
        ),
        sessions=[
            Session(
                "session_1_trajectory_parameter_extraction",
                [
                    "I'm a visual learner, could you show me a diagram for how to extract parameters from a trajectory equation?",
                    "That's helpful, thanks for the visual.",
                ],
            ),
            Session(
                "session_2_trajectory_comparison",
                [
                    "Now let's compare two trajectory equations - same visual style would help.",
                ],
            ),
        ],
    ),
    Persona(
        student_id="eval_vikram",
        display_name="Vikram",
        preferred_pace="moderate",
        interests=[],
        notes=(
            "Pure isolation check - no prior interaction of any kind. "
            "get_dpm must return not-found before this runs, and nothing "
            "from any other persona's sessions may appear here or leak out."
        ),
        sessions=[
            Session(
                "session_1_cold_start",
                [
                    "This is my first time here - can you explain the staircase projectile collision method?",
                ],
            ),
        ],
    ),
]
