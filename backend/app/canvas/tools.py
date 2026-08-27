"""The tutor's hands: ADK tools that write on the shared board and read it back.

Two design choices here are load-bearing.

**Anchors are marked up inline, not passed as a parallel list.** The model
writes `the [[vertical component|vector.decomposition]] decides it` and the
tool extracts the anchor from the text it is already writing. Passing spans
separately invites the one failure that silently breaks grounding — a span
that isn't in the text, so it renders as nothing and the student's gesture
resolves to something they never pointed at. Extracting from the text makes
that impossible rather than merely validated.

**Ids are minted here, never asked of the model.** Every write returns the id
it created, so `point_at` and `strike_block` can only ever name a block or
anchor that really exists. See app/canvas/doc.py:IdMinter.
"""
from __future__ import annotations

import logging
import re

from google.adk.tools import ToolContext

from app import sessions
from app.canvas import doc as D

log = logging.getLogger("nityam.canvas")

# [[span]] or [[span|concept.id]] — non-greedy, no nesting.
_MARKUP = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]")


def parse_markup(text: str) -> tuple[str, list[tuple[str, str | None]]]:
    """Strip [[...]] markers, returning the clean text and what to anchor.

    The span is taken *out of* the text, so it is present in the result by
    construction — there is no way for the two to disagree.
    """
    found: list[tuple[str, str | None]] = []

    def take(match: re.Match) -> str:
        span = match.group(1).strip()
        concept = (match.group(2) or "").strip() or None
        if span:
            found.append((span, concept))
        return span

    return _MARKUP.sub(take, text), found


def _anchors(state: sessions.SessionState, marked: list[tuple[str, str | None]]):
    return [
        D.Anchor(id=state.mint(f"a_{D.slug(span, 12)}"), span=span, concept=concept)
        for span, concept in marked
    ]


def _sid(tool_context: ToolContext) -> str:
    """The session id, seeded into ADK state when the session is created."""
    return tool_context.state.get("session_id") or "unknown"


def _publish(tool_context: ToolContext, patch, **extra) -> dict:
    session_id = _sid(tool_context)
    try:
        sessions.publish(session_id, patch)
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("patch rejected (%s): %s", patch.op, exc)
        return {"error": str(exc)}
    log.info("board %s: %s %s", session_id, patch.op, extra or "")
    return {"ok": True, **extra}


# ------------------------------------------------------------------ reading


def read_screen(tool_context: ToolContext) -> dict:
    """Read what is on the student's screen right now, before you change it.

    Call this before point_at, strike_block, or any reference to something
    already written — it is the only way to know the real block and anchor ids.
    Also tells you what the student last marked and where the simulation is set.

    Returns:
        dict with "blocks" (id, kind, text, struck, anchors), "simulation",
        "quiz", "lastMarked", and "topic".
    """
    state = sessions.get(_sid(tool_context))
    board = state.board
    return {
        "topic": board.pages[0].blocks[0].text if board.pages and board.pages[0].blocks else "",
        "blocks": [
            {
                "id": b.id,
                "kind": b.kind,
                "text": D.block_text(b)[:400],
                "struck": b.struck,
                "anchors": [
                    {"id": a.id, "span": a.span, "concept": a.concept}
                    for a in D.block_anchors(b)
                ],
            }
            for b in board.blocks()
        ],
        "simulation": state.screen.simulation,
        "quiz": state.screen.quiz,
        "lastMarked": state.screen.lastMarked,
    }


# ------------------------------------------------------------------ writing


def write_heading(text: str, tool_context: ToolContext) -> dict:
    """Start a new section on the board with a short heading.

    Args:
        text: The heading. A few words, not a sentence.

    Returns:
        dict with "block_id".
    """
    state = sessions.get(_sid(tool_context))
    block = D.Heading(id=state.mint("b_head"), text=text.strip())
    return _publish(tool_context, D.AppendBlock(block=block), block_id=block.id)


def write_note(text: str, tool_context: ToolContext) -> dict:
    """Write a paragraph of explanation on the board.

    Mark any term the student should be able to point at with double brackets,
    optionally naming the concept after a pipe:

        "The [[vertical component|vector.decomposition]] sets the height, not
        the [[launch speed|projectile.launch_speed]]."

    The brackets are stripped before it renders. Mark 1-3 terms per paragraph —
    marking everything makes nothing stand out, and marking nothing means the
    student can circle it and you learn nothing.

    Mark ideas and named quantities, not bare numbers: [[1]] or [[90]] will
    latch onto the first digit anywhere in the sentence and teaches nothing
    when pointed at.

    Args:
        text: The paragraph, with [[...]] markers around pointable terms.

    Returns:
        dict with "block_id" and "anchors" (the ids you can later point_at).
    """
    state = sessions.get(_sid(tool_context))
    clean, marked = parse_markup(text)
    anchors = _anchors(state, marked)
    try:
        block = D.TutorText(id=state.mint("b_note"), text=clean.strip(), anchors=anchors)
    except ValueError as exc:
        return {"error": str(exc)}
    return _publish(
        tool_context,
        D.AppendBlock(block=block),
        block_id=block.id,
        anchors=[a.id for a in anchors],
    )


def write_equation(formula: str, caption: str, tool_context: ToolContext) -> dict:
    """Put a formula on the board, written the way it goes on a blackboard.

    THERE IS NO LATEX HERE. The board renders plain text, so a backslash
    reaches the student as a literal backslash. Write real Unicode symbols:

        WRONG: R = \\frac{u^2 \\sin(2\\theta)}{g}
        RIGHT: R = u² sin(2θ) / g

        WRONG: 2\\theta = 90^\\circ \\implies \\theta = 45^\\circ
        RIGHT: 2θ = 90°, so θ = 45°

        WRONG: R_{max}
        RIGHT: R_max

    Use ² ³ √ θ π ° · × ≈ ≤ ≥ Δ directly. Write fractions on one line with a
    slash, and bracket the numerator if it needs it: (u sinθ)² / 2g.

    Mark the terms that carry meaning with [[...]] so the student can point at
    them, naming the concept after a pipe:

        "R = u² [[sin(2θ)|projectile.horizontal_range]] / g"

    Args:
        formula: The formula in blackboard notation, with [[...]] markers
            around pointable terms.
        caption: One short line under it saying what it is for. Pass "" for none.

    Returns:
        dict with "block_id" and "anchors".
    """
    state = sessions.get(_sid(tool_context))
    if "\\" in formula:
        return {
            "error": "that formula contains a backslash, so it is LaTeX. The "
            "board has no maths renderer — the student would see the backslashes. "
            "Rewrite it in blackboard notation with real symbols, e.g. "
            "'R = u² sin(2θ) / g', and call this again."
        }
    clean, marked = parse_markup(formula)
    anchors = _anchors(state, marked)
    try:
        block = D.Equation(
            id=state.mint("b_eq"),
            tex=clean.strip(),
            caption=caption.strip() or None,
            anchors=anchors,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return _publish(
        tool_context,
        D.AppendBlock(block=block),
        block_id=block.id,
        anchors=[a.id for a in anchors],
    )


def write_callout(tone: str, label: str, text: str, tool_context: ToolContext) -> dict:
    """Box something off from the running explanation.

    Args:
        tone: "correction" when fixing a wrong belief the student just showed,
            "finding" when recording something they worked out themselves.
        label: A short uppercase-style label, e.g. "WHERE THIS GOES WRONG".
        text: One or two sentences.

    Returns:
        dict with "block_id".
    """
    if tone not in ("correction", "finding"):
        return {"error": 'tone must be "correction" or "finding"'}
    state = sessions.get(_sid(tool_context))
    block = D.Callout(
        id=state.mint("b_call"), tone=tone, label=label.strip(), text=text.strip()
    )
    return _publish(tool_context, D.AppendBlock(block=block), block_id=block.id)


def point_at(anchor_ids: list[str], reason: str, tool_context: ToolContext) -> dict:
    """Highlight terms already on the board, so the student's eye goes there.

    Use this when you say "look at this bit" — otherwise the student has to
    guess which part of the page you mean. Anchor ids come from a write tool's
    result or from read_screen; inventing one is rejected.

    Args:
        anchor_ids: Anchor ids to light up. Usually one, at most three.
        reason: Why, in a few words. Not shown to the student; it goes in the log.

    Returns:
        dict confirming, or an error naming the ids that do not exist.
    """
    return _publish(
        tool_context,
        D.PointAt(anchorIds=list(anchor_ids), reason=reason),
        pointed=list(anchor_ids),
    )


def strike_block(block_id: str, tool_context: ToolContext) -> dict:
    """Cross out a block that turned out to be wrong or has been superseded.

    It stays visible, struck through — a corrected mistake teaches more than a
    mistake that quietly vanished. There is no delete.

    Args:
        block_id: From a write tool's result or read_screen.

    Returns:
        dict confirming, or an error if no such block is on the board.
    """
    return _publish(tool_context, D.Strike(blockId=block_id), block_id=block_id)


def scroll_to(block_id: str, tool_context: ToolContext) -> dict:
    """Scroll the student's page to a block, when it has moved off screen.

    Args:
        block_id: From read_screen.

    Returns:
        dict confirming, or an error if no such block is on the board.
    """
    return _publish(tool_context, D.Goto(blockId=block_id), block_id=block_id)


BOARD_TOOLS = [
    read_screen,
    write_heading,
    write_note,
    write_equation,
    write_callout,
    point_at,
    strike_block,
    scroll_to,
]
