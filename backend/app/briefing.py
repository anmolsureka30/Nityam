"""The voice layer's opening briefing.

VoiceAgent is allowed to answer from what is in front of it and forbidden from
inventing physics. Those two rules only add up to a fast tutor if something puts
the topic in front of it — otherwise every question, however small, has to go
down to the reasoning model and come back nine seconds later.

So before the first turn, this assembles one context injection: what the session
is for, what is on record about this student, and their own teacher's words on
tonight's topic with citations. It is delivered straight through the live
connection's own sink (see `brief_voice_layer`) — no queue, no background task.
It is also refreshed after every specialist call, since a specialist's own work
is exactly the moment the student's record is most likely to have changed — see
`agents/specialist_runner.refresh_brief`, which calls `compose_brief` below.

The split between `compose_brief` (assemble the text) and `brief_voice_layer`
(assemble it and send it) is what makes that refresh safe. Composing it means
several blocking Firestore round trips — measured at 3+ seconds — so the
refresh path runs `compose_brief` in a thread and only touches the sink, on the
event loop, if the text actually changed. Doing that with a function that
insisted on holding the sink itself would mean either blocking the loop for
three seconds mid-lesson or handing a live queue to a worker thread.

Called from main.py's `start` handler, which is guaranteed to run before the
greeting: the frontend sends `start` and `greet` on the same tick, in that order
(frontend/src/lib/live/useLiveSession.ts).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app import incoming, sessions
from app.memory import store

log = logging.getLogger("nityam.briefing")

MAX_CHUNKS = 12
"""How many lecture excerpts reach the voice layer.

Raised from 6. The Live API re-bills all of it every turn, so this is a real
cost — but the explicit priority for the demo is latency and how it feels, and
every chunk that is NOT here is a question she has to delegate and wait nine
seconds to answer. `_rank` below is what makes the extra six worth their
tokens rather than just louder."""

# Words that match half the syllabus and so tell us nothing about which concept
# the student pressed.
STOPWORDS = {
    "the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "is",
    "motion", "physics", "class", "chapter", "problem", "problems", "concept",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in STOPWORDS}


def load_record(student_id: str):
    """One trip to the store for the two documents the whole brief is built
    from: `(conn, dpm, teaching_memory)`.

    Both halves of the brief need both documents — `resolve_concepts` reads
    the weaknesses and open doubts for their concept ids, `_student_brief`
    reads the same two objects for their prose. They used to fetch
    independently, which meant four blocking Firestore round trips per brief
    instead of two, on a function that is now called after every single
    specialist call rather than once at session start.

    Returns `(None, None, None)` if the store is unreachable, and
    `(conn, None, None)` if the store is up but the reads fail — the caller
    can still use `conn` for the grounding index in that second case, which
    is what the original code did.
    """
    from app.memory.tools import shared_connection

    try:
        conn = shared_connection()
    except Exception:  # noqa: BLE001 - never block a lesson on the store
        log.warning("no store; the voice layer opens unbriefed")
        return None, None, None
    try:
        return (
            conn,
            store.get_dpm(conn, student_id),
            store.get_teaching_memory(conn, student_id),
        )
    except Exception:  # noqa: BLE001
        return conn, None, None


def resolve_concepts(plan, conn, dpm, memory) -> list[str]:
    """The plan's topic name -> real grounding concept ids.

    `plan.concept` is a syllabus code ("PHY-11-K2") and `plan.concept_name` is
    prose ("Maximum range"); neither is a grounding id. So match the name's words
    against the ids the index actually holds, and always fold in what this
    student is weak on or has an open doubt about — those are the things she has
    to be able to discuss the moment the session opens.

    Takes the already-fetched `conn`/`dpm`/`memory` from `load_record` rather
    than fetching its own: this and `_student_brief` want the identical two
    documents, and fetching them twice doubled the blocking round trips.
    """
    wanted: list[str] = []
    if conn is None:
        return []

    # 1. This student's own trouble spots, first — they are guaranteed real ids.
    if dpm is not None:
        wanted.extend(dpm.weaknesses)
    if memory is not None:
        wanted.extend(
            d.concept_id for d in memory.open_doubts if d.status != "resolved"
        )

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


def _rank(chunks: list[dict], plan) -> list[dict]:
    """The best chunks for tonight's topic, near-duplicates removed.

    `search_grounding` returns whatever matched, in whatever order the store
    produced. Two problems with taking the first N of that:

      * The corpus is machine-ingested lecture transcript and genuinely
        repeats itself — the same "highest vertical point attained by a
        projectile" paragraph came back twice in one real brief, under two
        different concept ids, costing double for one idea.
      * Some of it is OCR noise. One chunk's entire board content was
        `Pü! 244.064-0`.

    So: score by word overlap with the topic, drop anything that repeats an
    earlier chunk's opening, and prefer chunks that carry a real citation.
    Cheap, local, and no model — this runs on the session-start path.
    """
    topic = _tokens(f"{plan.concept_name} {plan.concept}")
    seen: set[str] = set()
    scored: list[tuple[float, int, dict]] = []

    for i, chunk in enumerate(chunks):
        text = " ".join((chunk.get("text") or "").split())
        if len(text) < 40:
            continue                      # a fragment teaches nothing
        # Near-duplicate: the transcript repeats whole paragraphs verbatim
        # across concepts, and the first eighty characters are enough to
        # recognise that without a similarity metric.
        head = text[:80].lower()
        if head in seen:
            continue
        seen.add(head)

        score = len(topic & _tokens(text)) / (len(topic) or 1)
        if chunk.get("location"):
            score += 0.15                 # a citable moment beats a floating one
        scored.append((score, -i, chunk))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [c for _, _, c in scored[:MAX_CHUNKS]]


def _last_time(conn, student_id: str) -> str:
    """One line about the previous session, or "".

    Session logs have been written since the memory layer existed and never
    read back. The distilled record says what the student knows; only this
    says where they actually stopped, which is what "last time we got as far
    as…" is made of.
    """
    if conn is None or store.latest_session_log is None:
        return ""
    try:
        # The latest session that actually SAYS something, not simply the
        # latest. Sessions written before close_session kept reflect()'s
        # summary have empty ones, and a run of those would otherwise hide a
        # perfectly good summary sitting just behind them.
        previous = store.latest_session_log(conn, student_id, with_summary=True)
    except Exception:  # noqa: BLE001 - never block a lesson on continuity
        log.warning("could not read the previous session", exc_info=True)
        return ""
    if previous is None or not (previous.summary or "").strip():
        return ""
    when = ""
    if previous.ended_at:
        days = (datetime.now(timezone.utc) - previous.ended_at).days
        when = "Earlier today" if days <= 0 else (
            "Yesterday" if days == 1 else f"{days} days ago")
        when += ", "
    return f"{when}last session: {' '.join(previous.summary.split())}"


def _student_brief(dpm, memory) -> str:
    """This student's record, as prose. Moved here from the retired
    TutorAgent — see git history for the original if needed.

    Handed the documents `load_record` already fetched, for the same reason
    `resolve_concepts` is: this used to open the store and read both of them
    a second time, on the same two ids, in the same function call."""
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


def compose_brief(session_id: str, student_id: str) -> str:
    """Assemble the briefing text and return it. Sends nothing.

    BLOCKING: several Firestore round trips, measured at 3+ seconds on a
    real store. Never call this straight from the event loop on a path that
    runs mid-lesson — `specialist_runner.refresh_brief` runs it through
    `asyncio.to_thread` for exactly that reason. The one place it is
    acceptable inline is the `start` handler, before the first turn, where
    there is nothing yet to stall."""
    state = sessions.get(session_id, student_id=student_id)
    conn, dpm, memory = load_record(student_id)
    concept_ids = resolve_concepts(state.plan, conn, dpm, memory)

    chunks: list[dict] = []
    if concept_ids:
        try:
            from app.memory.tools import search_grounding

            chunks = _rank(search_grounding(concept_ids)["chunks"], state.plan)
        except Exception:  # noqa: BLE001
            log.warning("grounding lookup failed; briefing without it", exc_info=True)

    brief = _student_brief(dpm, memory)
    last = _last_time(conn, student_id)
    if last:
        brief = f"{brief}\n- {last}"

    line = incoming.describe_grounding_pack(state.plan, brief, chunks)
    log.info(
        "composed the briefing: %s concept(s), %s chunk(s), %s chars",
        len(concept_ids), len(chunks), len(line),
    )
    log.debug("briefing in full:\n%s", line)
    return line


# The exact wording below is load-bearing: tests/test_routing.py's plumbing
# check greps the session log for "briefed the voice layer" to prove the
# briefing actually reached the model before the first turn. Splitting this
# function in two moved that line onto the compose half and quietly broke
# that check. It belongs on the half that does the delivering anyway.


def brief_voice_layer(session_id: str, student_id: str, sink) -> str:
    """Assemble and deliver the briefing directly through sink; return the
    text it sent.

    The session-start path. Refreshes during a lesson go through
    `specialist_runner.refresh_brief` instead, which composes off the event
    loop and only sends when the text actually changed — the returned text is
    what seeds that comparison, so the first refresh of a session doesn't
    re-send what the opening brief already said. (Nothing ever used the chunk
    count this used to return.)"""
    line = compose_brief(session_id, student_id)
    sink.text(line, partial=True)
    log.info("briefed the voice layer: %s chars", len(line))
    return line
