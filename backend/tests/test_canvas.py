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


async def main() -> int:
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

    # ------------------------------------------------- one call, many blocks
    sessions.drop("s_batch")
    batch = FakeToolContext("s_batch")
    sessions.get("s_batch")
    lesson = await T.write_lesson([
        "# Maximum range",
        "= R = u² [[sin(2θ)|projectile.horizontal_range]] / g | on flat ground",
        "Only the [[angle|projectile.launch_angle]] is yours to choose.",
        "! finding | WORTH KEEPING | The angle decides it.",
        "@ sin(2θ)",
    ], batch)
    check("write_lesson writes every block in one call",
          len(lesson.get("block_ids", [])) == 4, repr(lesson)[:120])
    made = sessions.get("s_batch").board.blocks()
    kinds = [b.kind for b in made]
    check("in the order given", kinds == ["heading", "heading", "equation", "tutor_text", "callout"],
          repr(kinds))
    eq = next(b for b in made if b.kind == "equation")
    check("the caption separator does not split the anchor markup",
          eq.tex == "R = u² sin(2θ) / g" and eq.caption == "on flat ground",
          f"{eq.tex!r} / {eq.caption!r}")
    check("and @ resolves to an anchor written in the same call",
          lesson.get("pointed_at") == [eq.anchors[0].id], repr(lesson.get("pointed_at")))
    callout = next(b for b in made if b.kind == "callout")
    check("blocks that carry no anchors still lose their markup",
          "[[" not in callout.text, callout.text[:50])
    # All-or-nothing: blocks are staged and validated before any is published,
    # so a bad line later in the list cannot leave half a lesson on the board.
    sessions.drop("s_none")
    none_ctx = FakeToolContext("s_none")
    before = len(sessions.get("s_none").board.blocks())
    broke = await T.write_lesson(
        ["# This heading is fine", "! only-two | parts"], none_ctx
    )
    after = len(sessions.get("s_none").board.blocks())
    check("a malformed line writes NOTHING rather than half a lesson",
          "error" in broke and after == before, f"{before} -> {after}; {broke}")
    check("LaTeX in a batch is refused too",
          "error" in await T.write_lesson(["= R = \\frac{a}{b}"], batch))

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

    # ---------------------------------------------------- the textbook index
    # "figure 3.14" — the single most natural way to ask — was the one phrasing
    # that returned nothing. The matcher did
    # `q.replace("fig.", "").replace("fig", "")`, which turns "figure 3.14" into
    # "ure 3.14", and then compared it for EXACT equality, so any surrounding
    # words missed too.
    from app.textbook import search_textbook

    def figure(query: str) -> list[dict]:
        return [h for h in search_textbook(query)["hits"] if h["kind"] == "figure"]

    for phrasing in ("3.14", "fig 3.14", "Fig. 3.14", "figure 3.14",
                     "show me figure 3.14 please", "bring up Figure 3.14"):
        found = figure(phrasing)
        check(f"the book finds a figure asked for as {phrasing!r}",
              len(found) == 1 and found[0]["page"] == 10,
              str(found))

    check("a figure that does not exist is not invented", not figure("figure 9.9"))
    check("a section can be asked for by number too",
          any(h["kind"] == "section" and h["page"] == 12
              for h in search_textbook("section 3.9")["hits"]),
          str(search_textbook("section 3.9")["hits"][:2]))
    check("and a plain topic still searches text",
          len(search_textbook("projectile")["hits"]) > 2)

    # ------------------------------------------------- the figure, not the page
    # "show me figure 3.14" used to put the whole printed page on the board and
    # leave the student to find the diagram on it. The index now records the
    # band each caption occupies, worked out from the caption's position and the
    # text above it.
    from app.textbook import _index, show_textbook_figure

    figures = [f for ch in _index() for f in ch["figures"]]
    boxed = [f for f in figures if f.get("box")]
    check("most figures know where they are on their page",
          len(boxed) / len(figures) > 0.8,
          f"{len(boxed)} of {len(figures)}")
    check("and every box is a plausible region, not a sliver or the whole sheet",
          all(0 < f["box"]["w"] <= 1 and 0.06 <= f["box"]["h"] <= 0.8
              and 0 <= f["box"]["x"] < 1 and 0 <= f["box"]["y"] < 1 for f in boxed),
          str([f for f in boxed
               if not (0.06 <= f["box"]["h"] <= 0.8)][:2]))

    class _Ctx:
        state = {"session_id": "s_fig"}

    sessions.get("s_fig")
    out = show_textbook_figure("keph103", 1, "look here", "3.14", _Ctx())
    placed = sessions.get("s_fig").board.blocks()[-1]
    check("asking for a numbered figure crops to it", placed.clip is not None,
          str(out))
    # The caller passed page 1. The index knows 3.14 is on page 10, and the
    # index wins: search_textbook can return the page that merely MENTIONS a
    # figure, and picking that one is an easy mistake to make.
    check("and it lands on the page the figure is actually printed on",
          placed.page == 10, f"page {placed.page}")

    out = show_textbook_figure("keph103", 12, "the whole page", "", _Ctx())
    whole = sessions.get("s_fig").board.blocks()[-1]
    check("asking for a page with no figure number shows the whole page",
          whole.clip is None and whole.page == 12, str(out))

    bad = show_textbook_figure("keph103", 1, "nope", "9.9", _Ctx())
    check("and a figure the chapter does not have is refused, with the list",
          "error" in bad and "9.9" in bad["error"], str(bad)[:110])

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    # sessions.get() builds an asyncio.Queue, which wants a loop on some
    # platforms; run inside one so the test matches how the server calls it.
    raise SystemExit(asyncio.run(main()))
