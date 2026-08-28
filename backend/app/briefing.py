"""The voice layer's opening briefing.

VoiceAgent is allowed to answer from what is in front of it and forbidden from
inventing physics. Those two rules only add up to a fast tutor if something puts
the topic in front of it — otherwise every question, however small, has to go
down to the reasoning model and come back nine seconds later.

So before the first turn, this assembles one context injection: what the session
is for, what is on record about this student, and their own teacher's words on
tonight's topic with citations. It is delivered straight through the live
connection's own sink (see `brief_voice_layer`) — no queue, no background task.
It is also refreshed once after every specialist call resolves (main.py's
`trace()`), since a specialist's own work is exactly the moment the student's
record is most likely to have changed.

Called from main.py's `start` handler, which is guaranteed to run before the
greeting: the frontend sends `start` and `greet` on the same tick, in that order
(frontend/src/lib/live/useLiveSession.ts).
"""
from __future__ import annotations

import logging
import re

from app import incoming, sessions
from app.memory import store

log = logging.getLogger("nityam.briefing")

MAX_CHUNKS = 6

# Words that match half the syllabus and so tell us nothing about which concept
# the student pressed.
STOPWORDS = {
    "the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "is",
    "motion", "physics", "class", "chapter", "problem", "problems", "concept",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in STOPWORDS}


def resolve_concepts(plan, student_id: str) -> list[str]:
    """The plan's topic name -> real grounding concept ids.

    `plan.concept` is a syllabus code ("PHY-11-K2") and `plan.concept_name` is
    prose ("Maximum range"); neither is a grounding id. So match the name's words
    against the ids the index actually holds, and always fold in what this
    student is weak on or has an open doubt about — those are the things she has
    to be able to discuss the moment the session opens.
    """
    wanted: list[str] = []
    from app.memory.tools import shared_connection

    try:
        conn = shared_connection()
    except Exception:  # noqa: BLE001 - never block a lesson on the store
        log.warning("no store; the voice layer opens unbriefed")
        return []

    # 1. This student's own trouble spots, first — they are guaranteed real ids.
    try:
        dpm = store.get_dpm(conn, student_id)
        if dpm is not None:
            wanted.extend(dpm.weaknesses)
        memory = store.get_teaching_memory(conn, student_id)
        if memory is not None:
            wanted.extend(
                d.concept_id for d in memory.open_doubts if d.status != "resolved"
            )
    except Exception:  # noqa: BLE001
        pass

    # 2. Whatever the topic name points at.
    words = _tokens(f"{plan.concept_name} {plan.concept}")
    if words and store.list_concept_ids is not None:
        try:
            for concept_id in store.list_concept_ids(conn):
                if words & _tokens(concept_id):
                    wanted.append(concept_id)
        except Exception:  # noqa: BLE001
            pass

    return list(dict.fromkeys(wanted))  # de-duplicated, order preserved


def _student_brief(student_id: str) -> str:
    """This student's record, as prose. Moved here from the retired
    TutorAgent — see git history for the original if needed."""
    from app.memory import store
    from app.memory.tools import shared_connection

    try:
        conn = shared_connection()
        dpm = store.get_dpm(conn, student_id)
        memory = store.get_teaching_memory(conn, student_id)
    except Exception:  # noqa: BLE001 - never block a lesson on the store
        return "Nothing on record for this student yet. Teach from scratch."

    if dpm is None and memory is None:
        return "Nothing on record for this student yet. Teach from scratch."

    lines: list[str] = []
    if dpm is not None:
        persona = dpm.persona
        bits = [
            f"pace {persona.preferred_pace}" if persona.preferred_pace else "",
            f"language {persona.language_mix}" if persona.language_mix else "",
            f"interests {', '.join(persona.interests)}" if persona.interests else "",
        ]
        shown = "; ".join(b for b in bits if b)
        if shown:
            lines.append(f"- Persona: {shown}.")
        for concept, weakness in dpm.weaknesses.items():
            lines.append(
                f"- {concept}: {weakness.mastery} ({weakness.strength}), "
                f"evidence {', '.join(weakness.evidence)}."
            )
        for note in dpm.self_reflection:
            if note.status == "active":
                lines.append(f"- Note to self: {note.note}")

    if memory is not None:
        lines.append(f"- Teaching mode that has been working: {memory.teaching_style.current_mode}.")
        for doubt in memory.open_doubts:
            if doubt.status != "resolved":
                lines.append(
                    f"- OPEN DOUBT on {doubt.concept_id}: {doubt.doubt} "
                    f"The correct understanding is: {doubt.correct_understanding}"
                )
        covered = [c for c, v in memory.covered.items() if v.status == "covered"]
        if covered:
            lines.append(f"- Already covered: {', '.join(covered)}.")

    return "\n".join(lines) if lines else "Nothing on record yet. Teach from scratch."


def brief_voice_layer(session_id: str, student_id: str, sink) -> int:
    """Assemble and deliver the briefing directly through sink. Returns how
    many chunks it carried. Called once at session start, and again after
    every specialist call resolves — a specialist's own work is exactly
    the moment the student's record is most likely to have changed."""
    state = sessions.get(session_id, student_id=student_id)
    concept_ids = resolve_concepts(state.plan, student_id)

    chunks: list[dict] = []
    if concept_ids:
        try:
            from app.memory.tools import search_grounding

            chunks = search_grounding(concept_ids)["chunks"][:MAX_CHUNKS]
        except Exception:  # noqa: BLE001
            log.warning("grounding lookup failed; briefing without it", exc_info=True)

    brief = _student_brief(student_id)

    line = incoming.describe_grounding_pack(state.plan, brief, chunks)
    sink.text(line, partial=True)
    log.info(
        "briefed the voice layer: %s concept(s), %s chunk(s), %s chars",
        len(concept_ids), len(chunks), len(line),
    )
    log.debug("briefing in full:\n%s", line)
    return len(chunks)
