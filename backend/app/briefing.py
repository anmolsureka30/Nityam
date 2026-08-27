"""The voice layer's opening briefing.

VoiceAgent is allowed to answer from what is in front of it and forbidden from
inventing physics. Those two rules only add up to a fast tutor if something puts
the topic in front of it — otherwise every question, however small, has to go
down to the reasoning model and come back nine seconds later.

So before the first turn, this assembles one context injection: what the session
is for, what is on record about this student, and their own teacher's words on
tonight's topic with citations. From then on the board pushes
(`incoming.describe_board_delta`) keep it current.

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
    try:
        conn = store.connect()
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


def brief_voice_layer(session_id: str, student_id: str) -> int:
    """Assemble and inject the briefing. Returns how many chunks it carried."""
    state = sessions.get(session_id, student_id=student_id)
    concept_ids = resolve_concepts(state.plan, student_id)

    chunks: list[dict] = []
    if concept_ids:
        try:
            from app.memory.tools import search_grounding

            chunks = search_grounding(concept_ids)["chunks"][:MAX_CHUNKS]
        except Exception:  # noqa: BLE001
            log.warning("grounding lookup failed; briefing without it", exc_info=True)

    brief = ""
    try:
        from app.agents.tutor_agent import _brief

        brief = _brief(student_id)
    except Exception:  # noqa: BLE001 - mock mode has no agent stack
        pass

    line = incoming.describe_grounding_pack(state.plan, brief, chunks)
    sessions.inject(session_id, line)
    log.info(
        "briefed the voice layer: %s concept(s), %s chunk(s), %s chars",
        len(concept_ids), len(chunks), len(line),
    )
    log.debug("briefing in full:\n%s", line)
    return len(chunks)
