"""Per-session server state: the board, the id minter, the frontend snapshot,
and the outbox the WebSocket drains.

These four live together on purpose. `publish()` has to apply a patch to the
board *and* enqueue it for the browser in one call — if those were separate
steps in separate modules, `read_screen()` could report a board the student
cannot see yet, and the tutor would point at a block that hasn't rendered.
(The plan called for three files: state.py, outbox.py, screen.py. Cohesion
won — one module, one lock, one seam.)

╔═ SEAM ════════════════════════════════════════════════════════════════════╗
║ Everything here is process memory. `_SESSIONS` is a plain dict, so a       ║
║ second Cloud Run instance sees none of it and a restart loses the board.   ║
║                                                                           ║
║   board       -> a Firestore document; the browser reads it with           ║
║                  onSnapshot instead of listening for canvas_patch frames   ║
║   outbox      -> the Firestore write itself (delete the queue entirely)    ║
║   screen      -> Memory Store / Redis, keyed by session id                 ║
║                                                                           ║
║ `publish()` is the single place a patch is written, so that swap is one    ║
║ function, not a sweep.                                                    ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.canvas import doc as D

log = logging.getLogger("nityam.sessions")

# STUB: the topic comes from the class recap Shruti produces overnight. Until
# that pipeline is wired, one env-overridable line.
OPENING_EYEBROW = os.getenv("NITYAM_TOPIC_EYEBROW", "Revision · today's class")
OPENING_HEADING = os.getenv("NITYAM_TOPIC_HEADING", "Maximum range — why 45° wins")
OPENING_CONCEPT = os.getenv("NITYAM_TOPIC_CONCEPT", "projectile.horizontal_range")


@dataclass
class Plan:
    """What this session is for.

    Three buttons on the home screen led to one identical conversation that
    opened by asking what the student wanted to do — which is the wrong
    question when they just pressed "Revise today's class" on a named concept.
    """

    mode: str = "doubt"          # revision | doubt | exam
    concept: str = ""
    concept_name: str = ""
    intensity: str = ""
    minutes: int = 0


@dataclass
class Screen:
    """What the student is looking at, as last reported by the browser.

    The tutor cannot see the page, so without this it is teaching blind: it
    would describe a simulation the student already moved, or ask them to look
    at something scrolled off screen.
    """

    simulation: dict = field(default_factory=dict)
    quiz: dict = field(default_factory=dict)
    visibleBlockIds: list[str] = field(default_factory=list)
    lastMarked: dict = field(default_factory=dict)
    updatedAt: str = ""


@dataclass
class SessionState:
    session_id: str
    student_id: str
    board: D.CanvasDoc
    minter: D.IdMinter
    screen: Screen
    plan: Plan
    outbox: asyncio.Queue
    """Things to say into the live conversation that nobody asked for — an
    artifact finishing in the background, mostly. Drained by main.py and sent
    as a completed turn, so she actually speaks it."""
    nudges: asyncio.Queue
    """Background work in flight. Held only so the event loop does not garbage
    collect a task nobody is awaiting."""
    jobs: set
    started_at: datetime

    def mint(self, prefix: str) -> str:
        return self.minter.next(prefix)


_SESSIONS: dict[str, SessionState] = {}


def _new_board(session_id: str) -> D.CanvasDoc:
    """A near-empty board: one heading, and nothing else.

    Deliberate. Every other block on screen got there because an agent called
    a write tool, so what you see is what the tutor actually did.
    """
    return D.CanvasDoc(
        id=f"nb_{session_id}",
        conceptId=OPENING_CONCEPT,
        pages=[
            D.Page(
                page=1,
                eyebrow=OPENING_EYEBROW,
                blocks=[D.Heading(id="b_topic", text=OPENING_HEADING)],
            )
        ],
    )


def get(session_id: str, student_id: str = "demo_student") -> SessionState:
    state = _SESSIONS.get(session_id)
    if state is None:
        state = SessionState(
            session_id=session_id,
            student_id=student_id,
            board=_new_board(session_id),
            minter=D.IdMinter(),
            screen=Screen(),
            plan=Plan(),
            outbox=asyncio.Queue(),
            nudges=asyncio.Queue(),
            jobs=set(),
            started_at=datetime.now(timezone.utc),
        )
        _SESSIONS[session_id] = state
        log.info("board created for session %s", session_id)
    return state


def drop(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def known(session_id: str) -> bool:
    return session_id in _SESSIONS


def nudge(session_id: str, text: str) -> None:
    """Interrupt the lesson with something worth saying.

    Used when work that was started in the background finishes — the tutor sent
    the student off to do something else and now needs to know it is ready.
    """
    state = _SESSIONS.get(session_id)
    if state is None:
        return
    try:
        state.nudges.put_nowait(text)
    except asyncio.QueueFull:  # pragma: no cover - unbounded queue
        log.warning("nudge dropped for %s", session_id)


def track(session_id: str, task) -> None:
    """Keep a reference to a fire-and-forget task.

    asyncio holds only a weak reference to a task nobody awaits, so without
    this the artifact generation can be collected mid-flight and simply never
    finish, with no error anywhere.
    """
    state = _SESSIONS.get(session_id)
    if state is None:
        return
    state.jobs.add(task)
    task.add_done_callback(state.jobs.discard)


# ------------------------------------------------------------------- publish


class PatchRejected(Exception):
    """A patch that would corrupt the board. Returned to the model as a tool
    error so it can correct itself, rather than raised at the student."""


def publish(session_id: str, patch) -> dict:
    """Apply one patch to the board and queue it for the browser.

    Returns a small summary for the tool result, so the model learns the id it
    just created without having to guess.
    """
    state = get(session_id)
    _apply(state, patch)

    try:
        state.outbox.put_nowait(patch)
    except asyncio.QueueFull:  # pragma: no cover - unbounded queue
        log.warning("outbox full for session %s; patch dropped", session_id)

    return {"ok": True, "op": patch.op}


def _apply(state: SessionState, patch) -> None:
    board = state.board

    if patch.op == "append_block":
        _reject_duplicate_ids(board, patch.block)
        board.page(patch.page).blocks.append(patch.block)

    elif patch.op == "replace_block":
        for page in board.pages:
            for i, existing in enumerate(page.blocks):
                if existing.id == patch.blockId:
                    page.blocks[i] = patch.block
                    return
        raise PatchRejected(f"no block {patch.blockId!r} on the board to replace")

    elif patch.op == "strike":
        block = board.find(patch.blockId)
        if block is None:
            raise PatchRejected(f"no block {patch.blockId!r} on the board")
        block.struck = True

    elif patch.op == "point_at":
        known_anchors = set(board.anchor_ids())
        missing = [a for a in patch.anchorIds if a not in known_anchors]
        if missing:
            raise PatchRejected(
                f"no anchors on the board with id(s) {missing}. "
                f"Call read_screen to see what is actually there."
            )

    elif patch.op == "goto":
        if board.find(patch.blockId) is None:
            raise PatchRejected(f"no block {patch.blockId!r} on the board")

    # show_quiz carries no board mutation — the modal is transient UI.


def _reject_duplicate_ids(board: D.CanvasDoc, block) -> None:
    if board.find(block.id) is not None:
        raise PatchRejected(f"block id {block.id!r} is already on the board")
    clashing = set(board.anchor_ids()) & {a.id for a in D.block_anchors(block)}
    if clashing:
        raise PatchRejected(f"anchor id(s) already in use: {sorted(clashing)}")
