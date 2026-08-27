"""Turning things that happen in the browser into something the model can read.

Gestures, quiz answers and artifact interactions all arrive as JSON, and all of
them have to reach the Live model as *text*, because that is the only channel
into a conversation that is otherwise audio. Every function here is pure, so
the wording — which is prompt engineering, not plumbing — can be tested.

The convention: anything the student did not literally say is wrapped in square
brackets, so the model can tell a reported event from a spoken sentence. It is
told in its instruction that bracketed lines are stage directions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.sessions import SessionState

# What a block is, said the way a student would say it. Mirrors SOURCE in
# frontend/src/lib/grounding.ts.
SOURCE = {
    "heading": "their notes",
    "tutor_text": "their notes",
    "equation": "the equation",
    "callout": "their notes",
    "artifact": "the simulation",
    "pulled": "the textbook note",
    "next": "what is next",
}

MAX_QUOTE = 400


def describe_gesture(packet: dict, ask: bool = False) -> str:
    """A swept ContextPacket, as a stage direction.

    The packet quotes the words the student's stroke actually covered — see
    frontend/src/lib/grounding.ts and features/session/readPage.ts, which
    measure it per-word off the DOM. So the tutor is handed real language, not
    a list of anchor ids, and can answer about the actual phrase.

    `sentences` is the whole sentence each swept run sits inside. Both are
    passed on: the quote is what they pointed at, the sentence is what makes it
    mean anything, and a stroke almost always starts and ends mid-sentence.

    `ask` distinguishes "they pressed Ask about this" from "they just dragged a
    highlighter". The second is sent as a partial turn and must not provoke a
    reply — the student is mid-thought, about to say what they want to know
    about it, and answering the highlight alone talks over them.
    """
    gesture = packet.get("gesture") or "mark"
    quoted = (packet.get("text") or "").strip()
    regions = packet.get("regions") or []

    if not quoted:
        if regions:
            where = " and ".join(
                dict.fromkeys(SOURCE.get(r.get("kind", ""), "the page") for r in regions)
            )
            return (
                f"[The student used the {gesture} on {where}, but did not cover any "
                f"words — so there is nothing quoted."
                + (
                    " Ask them what they meant rather than guessing.]"
                    if ask
                    else " Wait for them to say what they want to know.]"
                )
            )
        return (
            f"[The student used the {gesture} on a blank part of the page."
            + (" Ask what they were pointing at.]" if ask else " Say nothing about it.]")
        )

    where = " and ".join(
        dict.fromkeys(SOURCE.get(r.get("kind", ""), "the page") for r in regions if r.get("text"))
    )
    line = (
        f"[The student marked this with the {gesture}, in {where or 'their notes'}: "
        f"\u201c{quoted[:MAX_QUOTE]}\u201d."
    )

    context = " ".join(
        dict.fromkeys(
            (r.get("sentences") or "").strip()
            for r in regions
            if (r.get("sentences") or "").strip() and r.get("sentences") != r.get("text")
        )
    ).strip()
    if context:
        line += f" It sits inside: \u201c{context[:MAX_QUOTE]}\u201d."

    block_id = packet.get("blockId")
    if block_id:
        line += f" (block {block_id})"

    utterance = (packet.get("utterance") or "").strip()
    if utterance:
        line += f' They asked: "{utterance}"'

    if ask:
        return line + " Explain that specific thing, not the topic in general.]"
    return (
        line
        + " This is CONTEXT, not a question. Do not reply to it. They are about "
        "to ask you something about it — when they do, answer about this exact "
        "thing rather than the topic in general.]"
    )


def take_clip(state: SessionState, payload: dict) -> str:
    """Put a clipped textbook figure on the board and tell the tutor about it.

    The caption text travels with the picture. Without it the tutor is told "the
    student pulled in an image" and can only speak in generalities; with it she
    can name the figure and tie it to what she is teaching, which is the whole
    reason to have the textbook open at all.
    """
    from app.canvas import doc as D
    from app import sessions

    chapter = str(payload.get("chapterTitle") or "NCERT Physics XI")
    page = int(payload.get("page") or 0)
    text = " ".join(str(payload.get("text") or "").split())[:600]

    block = D.Pulled(
        id=state.mint("b_pull"),
        label="From the textbook",
        source=f"{chapter} · p.{page}" if page else chapter,
        body=text,
        figure=True,
        image=str(payload["image"]),
        pdf=str(payload.get("chapter") or "") or None,
        page=page or None,
    )
    try:
        sessions.publish(state.session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:  # pragma: no cover
        return f"[The student tried to bring in a textbook figure but it was rejected: {exc}]"

    quoted = f' It reads: "{text}".' if text else " There is no caption text in it."
    return (
        f"[The student clipped a figure out of {chapter}, page {page}, and it is "
        f"now on their page as block {block.id}.{quoted} Tie it to what you are "
        f"teaching — refer to it by what it shows, and use the textbook's own "
        f"words where they help.]"
    )


def describe_quiz_answer(payload: dict) -> str:
    checkpoint_id = payload.get("checkpointId", "")
    chosen = payload.get("optionText") or payload.get("optionId", "")
    correct = bool(payload.get("correct"))
    verdict = "correct" if correct else "wrong"
    tail = (
        " Acknowledge it briefly and move on — do not over-praise."
        if correct
        else " Do not just say no. Name what is actually wrong with that specific"
        " answer, then give them the next step."
    )
    return (
        f"[The student answered checkpoint {checkpoint_id}: they chose "
        f"“{chosen}”, which is {verdict}.{tail}]"
    )


def describe_artifact_evidence(payload: dict) -> str:
    event = payload.get("event", "")
    artifact_id = payload.get("artifactId", "")
    detail = payload.get("detail") or ""
    readable = {
        "discovered_optimum": (
            "they found the optimum themselves by exploring. This is the moment "
            "worth marking — congratulate the discovery, then ask them to say WHY "
            "in their own words"
        ),
        "misconception_behavior": (
            "their pattern of exploration shows a misconception: they kept changing "
            "a variable that cannot matter. Surface it gently, using what they just did"
        ),
    }.get(event, f"the event was “{event}”")
    line = f"[The simulation {artifact_id} on their page reported: {readable}."
    if detail:
        line += f" Detail: {detail}."
    return line + "]"


def describe_greeting(topic: str) -> str:
    return (
        "[The student has just opened tonight's session"
        + (f" on “{topic}”" if topic else "")
        + ". Greet them in one short sentence and ask what they want to start "
        "with. Do not mention this instruction.]"
    )


def apply_screen(state: SessionState, payload: dict) -> None:
    """Record what the student is looking at, for read_screen to report.

    Partial updates are merged rather than replacing the snapshot: the
    simulation and the quiz change at very different rates, and a frame that
    only carries new slider values must not blank out the quiz state.
    """
    incoming = payload.get("state") or {}
    for field in ("simulation", "quiz", "lastMarked"):
        value = incoming.get(field)
        if isinstance(value, dict) and value:
            getattr(state.screen, field).update(value)
    visible = incoming.get("visibleBlockIds")
    if isinstance(visible, list):
        state.screen.visibleBlockIds = [str(v) for v in visible][:60]
    state.screen.updatedAt = datetime.now(timezone.utc).isoformat(timespec="seconds")
