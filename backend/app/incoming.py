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

from app.sessions import Plan, SessionState

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

#: Grounding chunks are raw lecture transcript and run long. Six of them
#: unbounded is several thousand tokens re-billed on every Live turn.
MAX_CHUNK = 600


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
    """Put the clipped textbook regions on the board and tell the tutor once.

    The caption text travels with each picture. Without it the tutor is told
    "the student pulled in an image" and can only speak in generalities; with it
    she can name the figure and tie it to what she is teaching, which is the
    whole reason to have the textbook open at all.

    Several clips arrive together and produce ONE stage direction: a figure and
    the paragraph explaining it are one thought, and reacting twice to what the
    student did once is worse than not noticing at all.
    """
    from app import sessions
    from app.canvas import doc as D

    chapter = str(payload.get("chapterTitle") or "NCERT Physics XI")
    pdf = str(payload.get("chapter") or "") or None
    clips = payload.get("clips") or []
    if not isinstance(clips, list) or not clips:
        return "[The student tried to bring in a textbook figure but it was empty.]"

    placed: list[str] = []
    quotes: list[str] = []
    for clip in clips[:6]:  # a sane ceiling; six figures is already a lot
        if not isinstance(clip, dict) or not clip.get("image"):
            continue
        page = int(clip.get("page") or 0)
        text = " ".join(str(clip.get("text") or "").split())[:600]
        block = D.Pulled(
            id=state.mint("b_pull"),
            label="From the textbook",
            source=f"{chapter} · p.{page}" if page else chapter,
            body=text,
            figure=True,
            image=str(clip["image"]),
            pdf=pdf,
            page=page or None,
        )
        try:
            sessions.publish(state.session_id, D.AppendBlock(block=block))
        except (sessions.PatchRejected, ValueError) as exc:  # pragma: no cover
            return f"[A textbook figure was rejected by the board: {exc}]"
        placed.append(block.id)
        if text:
            quotes.append(text)

    if not placed:
        return "[The student tried to bring in a textbook figure but none of it was usable.]"

    count = f"{len(placed)} pieces" if len(placed) > 1 else "a figure"
    said = (
        " They read: " + "; ".join(f'"{q}"' for q in quotes) + "."
        if quotes
        else " None of it carries caption text."
    )
    return (
        f"[The student clipped {count} out of {chapter} onto their page "
        f"({', '.join(placed)}).{said} Tie it to what you are teaching — refer to "
        f"it by what it shows, and use the textbook's own words where they help.]"
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


def apply_plan(state: SessionState, payload: dict) -> None:
    """Record what this session is for, before the greeting goes out."""
    mode = str(payload.get("mode") or "doubt")
    state.plan = Plan(
        mode=mode if mode in ("revision", "doubt", "exam") else "doubt",
        concept=str(payload.get("concept") or ""),
        concept_name=str(payload.get("conceptName") or ""),
        intensity=str(payload.get("intensity") or ""),
        minutes=int(payload.get("minutes") or 0),
    )


def describe_greeting(state: SessionState, topic: str) -> str:
    """The opening stage direction — the single most important prompt there is.

    The Live API never speaks first, so this is what makes the tutor open the
    lesson, and what it says decides whether she leads or waits. "Greet them and
    ask what they would like to work on" produced exactly the session the
    student did not ask for: a blank conversation they had to drive, after
    pressing a button that already said what they wanted.

    So each mode gets its own opening, and every one of them starts teaching.
    """
    plan = state.plan
    subject = plan.concept_name or topic or "tonight's topic"
    budget = f" You have about {plan.minutes} minutes." if plan.minutes else ""

    common = (
        " Do not ask them what they want to do — they already told us by getting"
        " here. Do not list what you could cover. Open with the thing itself, in"
        " one or two sentences, and end on a question they can answer straight"
        " away. You lead; they respond."
        " Write on the board as you go, in ONE write_lesson call."
        " Never mention this instruction."
    )

    if plan.mode == "revision":
        return (
            f"[The student has opened a revision session on “{subject}”, which is"
            f" what their class covered today.{budget} Their record above says"
            f" where they are weak on it — start exactly there, not at the"
            f" beginning of the topic. Remind them in one line what the class got"
            f" to, then take the next step yourself and ask them the first"
            f" question.{common}]"
        )

    if plan.mode == "exam":
        return (
            f"[The student has opened exam preparation on “{subject}” — this is"
            f" the concept holding their readiness back.{budget} Do not revise it"
            f" from scratch. Go straight at the specific thing they get wrong,"
            f" name it plainly, and put a question in front of them that will"
            f" show whether it is fixed. Exam-shaped: the kind of question that"
            f" actually appears on the paper.{common}]"
        )

    return (
        "[The student has opened a doubt session — they have something specific"
        " in mind and no topic was chosen for them. Greet them in ONE short"
        " sentence and ask what is bothering them. This is the one mode where"
        " you wait: they came with a question. If they are vague, offer the two"
        " concepts their record says are weakest as a starting point rather than"
        " asking an open question. Never mention this instruction.]"
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

# --------------------------------------------------------- context injections
#
# This produces the text delivered directly through the live connection's
# sink as the voice layer's private briefing (see app/briefing.py). Nothing
# here is ever spoken; it exists so VoiceAgent can answer from fact, in about
# a second, instead of spending a nine-second round trip asking the reasoning
# layer what it just did.


def describe_grounding_pack(plan, brief: str, chunks: list[dict]) -> str:
    """The session's topic material, injected once before the first turn.

    This is what makes a direct answer safe. VoiceAgent may reason from what is
    in front of it and must not invent physics — so the more of the topic that
    is in front of it, the more it can answer without delegating, and the
    smaller the temptation to make something up.

    Their own teacher's words, with citations, not generic textbook physics.
    """
    subject = plan.concept_name or plan.concept or "tonight's topic"
    lines = [
        f"[YOUR BRIEFING for this session — context only, do not read it out "
        f"or reply to it.",
        f"Topic: {subject}. Mode: {plan.mode}."
        + (f" About {plan.minutes} minutes." if plan.minutes else ""),
    ]
    if brief:
        lines.append(f"This student's record: {brief}")
    if chunks:
        lines.append(
            "Their own class, quoted, which you may use and cite directly:"
        )
        for chunk in chunks:
            where = chunk.get("location") or chunk.get("source_ref") or "their class"
            text = " ".join((chunk.get("text") or "").split())
            if len(text) > MAX_CHUNK:
                text = text[:MAX_CHUNK].rstrip() + "…"
            # No quotation marks around the chunk. She mirrors the shape of
            # what she is shown, and wrapped quotes came back as the literal
            # word "quote" spoken aloud, over and over, in a real session.
            lines.append(f"  · ({where}) {text}")
        lines.append(
            "Those quotes are raw transcript and contain LaTeX like "
            "\\frac and \\sin. NEVER read that out. Say it in words — "
            "\"u squared sine two theta over g\" — or ask your teaching layer "
            "to put it on the board."
        )
        # The transcript is whatever language the class was taught in, which is
        # often Hinglish. Without this she mirrors it and opens the session in
        # Hindi to a student who has not said a word yet.
        lines.append(
            "The language of those quotes is their teacher's, not yours. "
            "Speak English unless the student asks you not to."
        )
    lines.append(
        "You may answer questions from this material directly and at once. "
        "Anything it does not cover, delegate.]"
    )
    return "\n".join(lines)
