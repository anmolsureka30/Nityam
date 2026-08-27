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

from app import logs, sessions
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


def split_outside_markup(text: str, limit: int = -1) -> list[str]:
    """Split on `|`, but not on the `|` inside a [[span|concept]] marker.

    A naive split cut `= R = u² [[sin(2θ)|projectile.range]] / g | caption` at
    the FIRST pipe — the one inside the anchor — and produced a formula reading
    "R = u² [[sin(2θ)" with the markup still in it. The two syntaxes share a
    delimiter, so the split has to know about the brackets.
    """
    parts, buf, depth = [], [], 0
    i = 0
    while i < len(text):
        if text.startswith("[[", i):
            depth += 1
            buf.append("[["); i += 2; continue
        if text.startswith("]]", i):
            depth = max(0, depth - 1)
            buf.append("]]"); i += 2; continue
        if text[i] == "|" and depth == 0 and (limit < 0 or len(parts) < limit):
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(text[i]); i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _anchors(state: sessions.SessionState, marked: list[tuple[str, str | None]]):
    return [
        D.Anchor(id=state.mint(f"a_{D.slug(span, 12)}"), span=span, concept=concept)
        for span, concept in marked
    ]


def _sid(tool_context: ToolContext) -> str:
    """The session id, seeded into ADK state when the session is created."""
    return tool_context.state.get("session_id") or "unknown"


def _brief_voice(session_id: str, blocks: list, pointed: list[str] | None = None) -> None:
    """Tell the voice layer what just appeared, as context it must not reply to.

    Called from every successful write. Without it VoiceAgent has to spend a
    round trip asking what the board says before it can answer the simplest
    question about it — three of eleven ask_tutor calls in the reference session
    resolved to nothing but a point_at, at 7.8s, 9.0s and 16.7s.
    """
    from app import incoming

    line = incoming.describe_board_delta(blocks, pointed)
    if line:
        sessions.inject(session_id, line)


def _publish(tool_context: ToolContext, patch, **extra) -> dict:
    session_id = _sid(tool_context)
    try:
        sessions.publish(session_id, patch)
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("patch rejected (%s): %s", patch.op, exc)
        return {"error": str(exc)}
    log.info("board %s: %s %s", session_id, patch.op, extra or "")
    # A newly appended block is the only patch that puts something on the page
    # the voice layer could not already name. point_at/strike/scroll only move
    # attention around blocks it has already been told about.
    block = getattr(patch, "block", None)
    if block is not None:
        _brief_voice(session_id, [block])
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


# ─────────────────────────────────────────────────────────────────────────────


def write_lesson(blocks: list[str], tool_context: ToolContext) -> dict:
    """Write a whole answer on the board in ONE call. Use this, not the
    single-block tools, for anything longer than one block.

    Every tool call is a separate round trip to the model — emit the call, wait,
    read the result, decide again — and each one is several seconds of silence
    for a student who is sitting there listening to nothing. Writing a heading,
    a formula and a paragraph as three calls took 27 seconds; as one call it is
    one round trip.

    Pass an ordered list of lines, each prefixed by what it is:

        "# Maximum range"                      a heading
        "= R = u² [[sin(2θ)|concept.id]] / g | range on flat ground"
                                               a formula, caption after the |
        "For a fixed [[speed|concept.id]]…"    a paragraph (no prefix)
        "! finding | YOU WORKED THIS OUT | The angle is the only thing…"
                                               a callout: tone | LABEL | text
        "@ sin(2θ)"                            highlight a term written above

    Formulas are blackboard notation, never LaTeX. Mark pointable terms with
    [[span]] or [[span|concept.id]] as usual. Put "@ term" last to draw their
    eye to something you just wrote.

    Args:
        blocks: The lines, in the order they should appear.

    Returns:
        dict with "block_ids" and "anchors", or {"error": ...} if a line was
        malformed — in which case NOTHING is written, so fix it and resend the
        whole list rather than patching up.
    """
    state = sessions.get(_sid(tool_context))
    staged: list = []
    pointed: list[str] = []
    span_to_anchor: dict[str, str] = {}

    for raw in blocks:
        line = str(raw).strip()
        if not line:
            continue

        if line.startswith("@"):
            pointed.append(line[1:].strip())
            continue

        if line.startswith("#"):
            # No anchors on a heading, but raw [[…]] on screen is worse than
            # dropping the marker, so strip rather than pass through.
            staged.append(
                D.Heading(id=state.mint("b_head"), text=parse_markup(line[1:].strip())[0])
            )
            continue

        if line.startswith("!"):
            parts = split_outside_markup(line[1:], 2)
            if len(parts) < 3:
                return {"error": f'callout needs "! tone | LABEL | text", got {line[:70]!r}'}
            tone, label, text = parts
            if tone not in ("correction", "finding"):
                return {"error": f'callout tone must be correction or finding, got {tone!r}'}
            staged.append(
                D.Callout(
                    id=state.mint("b_call"), tone=tone,
                    label=parse_markup(label)[0], text=parse_markup(text)[0],
                )
            )
            continue

        if line.startswith("="):
            pieces = split_outside_markup(line[1:], 1)
            body, caption = pieces[0], (pieces[1] if len(pieces) > 1 else "")
            if "\\" in body:
                return {"error": "that formula is LaTeX. Blackboard notation only, e.g. 'R = u² sin(2θ) / g'"}
            clean, marked = parse_markup(body)
            anchors = _anchors(state, marked)
            try:
                block = D.Equation(
                    id=state.mint("b_eq"), tex=clean, caption=caption or None,
                    anchors=anchors,
                )
            except ValueError as exc:
                return {"error": str(exc)}
            staged.append(block)
            span_to_anchor.update({a.span: a.id for a in anchors})
            continue

        clean, marked = parse_markup(line)
        anchors = _anchors(state, marked)
        try:
            block = D.TutorText(id=state.mint("b_note"), text=clean, anchors=anchors)
        except ValueError as exc:
            return {"error": str(exc)}
        staged.append(block)
        span_to_anchor.update({a.span: a.id for a in anchors})

    if not staged:
        return {"error": "nothing to write"}

    session_id = _sid(tool_context)
    written: list[str] = []
    for block in staged:
        try:
            sessions.publish(session_id, D.AppendBlock(block=block))
        except (sessions.PatchRejected, ValueError) as exc:
            return {"error": str(exc), "written_before_failing": written}
        written.append(block.id)

    lit: list[str] = []
    for span in pointed:
        anchor = span_to_anchor.get(span) or next(
            (a for sp, a in span_to_anchor.items() if span and span in sp), None
        )
        if anchor:
            lit.append(anchor)
    if lit:
        try:
            sessions.publish(session_id, D.PointAt(anchorIds=lit, reason="just written"))
        except (sessions.PatchRejected, ValueError):
            pass

    log.info("board %s: wrote %s block(s) in one call", session_id, len(written))
    logs.count("board block", len(written))
    # ONE injection for the whole batch. Five separate ones would read to the
    # voice layer as five teaching moves rather than one lesson.
    _brief_voice(session_id, staged, lit)
    return {
        "block_ids": written,
        "anchors": sorted(span_to_anchor.values()),
        "pointed_at": lit,
    }


BOARD_TOOLS = [
    write_lesson,
    read_screen,
    write_heading,
    write_note,
    write_equation,
    write_callout,
    point_at,
    strike_block,
    scroll_to,
]
