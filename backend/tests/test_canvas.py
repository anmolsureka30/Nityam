"""The board, with no model in the loop.

These are the invariants that make grounding work at all: an anchor whose span
isn't in its text is unpointable, a duplicate id silently shadows a block, and
pointing at an anchor that doesn't exist tells the student to look at nothing.
Every one of those renders perfectly and is wrong, which is why they are tested
here rather than noticed in a demo.

    .venv/bin/python -m tests.test_canvas
"""
from __future__ import annotations

import asyncio

from app import sessions
from app.canvas import doc as D
from app.canvas import tools as T

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


class FakeToolContext:
    """Stands in for ADK's ToolContext: the tools only read `state`."""

    def __init__(self, session_id: str) -> None:
        self.state = {"session_id": session_id, "student_id": "demo_student"}


def main() -> int:
    ctx = FakeToolContext("s_test")
    sessions.drop("s_test")

    # ---------------------------------------------------------- markup parsing
    clean, marked = T.parse_markup(
        "The [[vertical component|vector.decomposition]] sets it, not [[u]]."
    )
    check(
        "markup strips brackets and keeps the words",
        clean == "The vertical component sets it, not u.",
        repr(clean),
    )
    check(
        "markup extracts spans and concepts",
        marked == [("vertical component", "vector.decomposition"), ("u", None)],
        repr(marked),
    )

    # A span extracted from the text is present in the text by construction.
    for span, _ in marked:
        check(f"extracted span {span!r} occurs in the clean text", span in clean)

    # ---------------------------------------------------------- the empty board
    state = sessions.get("s_test")
    check("a new board has exactly one block", len(state.board.blocks()) == 1,
          f"{[b.kind for b in state.board.blocks()]}")
    check("that block is the topic heading", state.board.blocks()[0].kind == "heading")

    # ---------------------------------------------------------- writing
    result = T.write_equation(
        "R = u² [[sin(2θ)|projectile.horizontal_range]] / g", "the whole story", ctx
    )
    check("write_equation succeeds", result.get("ok") is True, repr(result))
    check("it returns the block id it minted", bool(result.get("block_id")), repr(result))
    check("it returns the anchor ids", len(result.get("anchors", [])) == 1, repr(result))
    eq_anchor = result["anchors"][0]

    board_eq = state.board.find(result["block_id"])
    check("the equation reached the board", board_eq is not None)
    check("the brackets did not", board_eq is not None and "[[" not in board_eq.tex,
          board_eq.tex if board_eq else "")

    note = T.write_note("Only the [[angle|projectile.launch_angle]] is yours.", ctx)
    check("write_note succeeds", note.get("ok") is True, repr(note))

    # ---------------------------------------------------------- the anchor gate
    try:
        D.Equation(id="b_x", tex="R = u sin(2t) / g",
                   anchors=[D.Anchor(id="a_x", span="cos(2t)")])
        check("an anchor span absent from the text is rejected", False, "it was accepted")
    except ValueError as exc:
        check("an anchor span absent from the text is rejected", True,
              str(exc).split(".")[0][:60])

    # ---------------------------------------------------------- id collisions
    try:
        sessions.publish("s_test", D.AppendBlock(block=D.Heading(id="b_topic", text="dup")))
        check("a duplicate block id is rejected", False, "it was accepted")
    except sessions.PatchRejected:
        check("a duplicate block id is rejected", True)

    # ---------------------------------------------------------- pointing
    pointed = T.point_at([eq_anchor], "explaining the sine term", ctx)
    check("point_at accepts a real anchor", pointed.get("ok") is True, repr(pointed))

    ghost = T.point_at(["a_does_not_exist"], "nothing", ctx)
    check("point_at rejects an invented anchor", "error" in ghost, repr(ghost))
    check("and says which one", "a_does_not_exist" in ghost.get("error", ""))

    # ---------------------------------------------------------- striking
    struck = T.strike_block(result["block_id"], ctx)
    check("strike_block marks it struck",
          struck.get("ok") is True and state.board.find(result["block_id"]).struck)
    check("striking a ghost block errors", "error" in T.strike_block("b_nope", ctx))

    # ---------------------------------------------------------- read_screen
    screen = T.read_screen(ctx)
    ids = [b["id"] for b in screen["blocks"]]
    check("read_screen sees every block", len(ids) == 3, repr(ids))
    check("read_screen reports struck state",
          any(b["struck"] for b in screen["blocks"]))
    check("read_screen exposes anchor ids the model can point at",
          eq_anchor in [a["id"] for b in screen["blocks"] for a in b["anchors"]])

    # ---------------------------------------------------------- the outbox
    drained = []
    while not state.outbox.empty():
        drained.append(state.outbox.get_nowait())
    ops = [p.op for p in drained]
    check("every accepted patch was queued for the browser, in order",
          ops == ["append_block", "append_block", "point_at", "strike"], repr(ops))
    check("rejected patches were NOT queued", "show_quiz" not in ops)

    # ---------------------------------------------------------- quiz shape
    try:
        D.Checkpoint(
            id="c1", question="?",
            options=[
                D.CheckpointOption(id="a", letter="A", text="x", correct=True),
                D.CheckpointOption(id="b", letter="B", text="y", correct=True),
            ],
        )
        check("a checkpoint with two right answers is rejected", False, "accepted")
    except ValueError:
        check("a checkpoint with two right answers is rejected", True)

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    # sessions.get() builds an asyncio.Queue, which wants a loop on some
    # platforms; run inside one so the test matches how the server calls it.
    async def _run():
        return main()

    raise SystemExit(asyncio.run(_run()))
