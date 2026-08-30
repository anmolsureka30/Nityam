"""The NCERT chapters the tutor can reach for.

The index is extracted from the real PDFs by
`frontend/scripts/build-textbook-index.mjs`, not hand-written — the current
edition renumbered its chapters (Motion in a Plane is 3, not 4), and hand-typed
page numbers would have been silently wrong from the day they were written.

Nothing here rasterises a page. The browser already has PDF.js and the file, so
a figure the tutor asks for travels as "chapter + page" and is rendered there —
which keeps a megabyte of base64 off the wire and a PDF renderer out of the
backend.
"""
from __future__ import annotations

import functools
import json
import logging
import re
from pathlib import Path

from google.adk.tools import ToolContext

from app import logs, sessions
from app.canvas import doc as D

log = logging.getLogger("nityam.textbook")

INDEX_PATH = Path(__file__).resolve().parent / "textbook_index.json"


@functools.cache
def _index() -> list[dict]:
    """The chapter index, parsed once.

    Cached because it is a 101 KB JSON file and this was re-reading and
    re-parsing it on EVERY call — once per search_textbook, once per
    show_textbook_figure, and now once per fast-path resolve. It is a build
    artefact that cannot change while the process runs.
    """
    try:
        return json.loads(INDEX_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        log.warning("no textbook index at %s", INDEX_PATH)
        return []


FIGURE_RE = re.compile(r"\b(?:fig(?:ure)?\.?\s*)?(\d{1,2}\.\d{1,2})\b", re.I)


def resolve_figure(query: str) -> dict | None:
    """A figure number in the student's words -> exactly where it is. No model.

    "show me figure 3.14" needs no reasoning: the number is a regex away and
    the index maps it straight to a chapter, a page and a crop box. Routing
    that through a specialist cost a full gemini-3.7-flash turn — around eight
    seconds — to make two lookups that take under a millisecond.

    Returns None when there is no number, or the number is not a real figure,
    and the caller falls through to TextbookAgent for anything vaguer than
    this ("that diagram with the two vectors").
    """
    match = FIGURE_RE.search(query or "")
    if not match:
        return None
    want = match.group(1)
    # The chapter is the part before the dot — NCERT numbers figures
    # chapter-first — but scan them all rather than trusting that, since the
    # index is small and a mismatch would silently show the wrong page.
    for chapter in _index():
        for figure in chapter.get("figures", []):
            if figure.get("figure") == want:
                return {
                    "chapter": chapter["file"],
                    "number": chapter["number"],
                    "title": chapter["title"],
                    "page": figure["page"],
                    "box": figure.get("box"),
                    "caption": figure.get("caption", ""),
                    "figure": want,
                }
    return None


def search_textbook(query: str, tool_context: ToolContext | None = None) -> dict:
    """Find where something is covered in the student's own NCERT textbook.

    Search the section headings, figure numbers, and figure captions of the
    four Class XI Physics chapters that are loaded — so a figure can be found
    by what it shows ("the diagram with two vectors added") as well as by its
    number. Use it before claiming the book says anything, and to find the
    page a figure is on so you can put it on their board.

    Args:
        query: A topic, section title, figure number, or a description of
            what a figure shows — "projectile", "friction", "13.3",
            "Fig 3.14", "diagram of two vectors being added".

    Returns:
        dict with "hits": chapters, sections and figures that match, each with
        the `chapter` id and `page` that show_textbook_figure needs. After two
        calls in a row with nothing placed on the board, also carries a "hint"
        telling the tutor to stop searching — confirmed live: a search that
        never lands anything can otherwise retry with a new phrasing
        indefinitely, once burning 70 seconds and four tries on one request.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"hits": [], "note": "give me something to look for"}

    # Words worth matching individually when the whole phrase never appears
    # verbatim anywhere — "projectile motion maximum height" never occurs as
    # one literal string in a section title, but "projectile" does. Confirmed
    # live: this exact multi-word phrasing returned zero hits every time.
    # Short words (of, the, in, at...) are skipped so they don't match
    # everything indiscriminately.
    _words = [w for w in q.split() if len(w) >= 4]

    def _matches(text: str) -> bool:
        return q in text or any(w in text for w in _words)

    # A numbered reference anywhere in the query. The old code did
    # `q.replace("fig.", "").replace("fig", "").strip() == fig["figure"]`, which
    # turns "figure 3.14" into "ure 3.14" and matches nothing — so the single
    # most natural way to ask for a figure was the one phrasing that failed. An
    # exact match also meant "show me figure 3.14" missed. Pull the number out
    # and compare that: "3.14", "fig 3.14", "figure 3.14", "Fig. 3.14",
    # "section 3.9" and any sentence containing one all work.
    numbered = re.search(r"\b(\d+\.\d+)\b", q)
    number = numbered.group(1) if numbered else None

    hits: list[dict] = []
    for ch in _index():
        label = f"Ch {ch['number']} · {ch['title']}"
        if _matches(ch["title"].lower()):
            hits.append({"kind": "chapter", "chapter": ch["file"], "title": label, "page": 1})
        for sec in ch["sections"]:
            if _matches(sec["title"].lower()) or number == sec["section"]:
                hits.append({
                    "kind": "section", "chapter": ch["file"], "page": sec["page"],
                    "title": f"{sec['section']} {sec['title'].title()}", "in": label,
                })
        for pg in ch.get("pageText", []):
            if _matches(pg["words"]):
                hits.append({
                    "kind": "page", "chapter": ch["file"], "page": pg["page"],
                    "title": f"{label}, page {pg['page']} mentions “{query.strip()}”",
                    "in": label,
                })
        for fig in ch["figures"]:
            caption = fig.get("caption", "")
            # A bare number query ("3.14") must only match that exact figure
            # number, never a caption's text -- "3.14" is a substring of
            # "Fig. 13.14 ...", so without this guard asking for one figure
            # by number also matched an unrelated figure eleven pages away.
            bare_number_query = q == number
            if number == fig["figure"] or (not bare_number_query and _matches(caption.lower())):
                title = f"Fig. {fig['figure']}"
                if caption:
                    title += f" — {caption[:100]}"
                hits.append({
                    "kind": "figure", "chapter": ch["file"], "page": fig["page"],
                    "title": title, "in": label,
                })
    result = {"hits": hits[:12], "found": len(hits)}

    if tool_context is not None:
        streak = tool_context.state.get("textbook_search_streak", 0) + 1
        if streak >= 2:
            result["hint"] = (
                "That is two searches in a row without placing a figure. Stop "
                "here — tell the student plainly that the book doesn't seem to "
                "have this, and teach on without it. Do not search again for "
                "this."
            )
            streak = 0
        tool_context.state["textbook_search_streak"] = streak

    return result


def show_textbook_figure(
    chapter: str, page: int, caption: str, figure: str, tool_context: ToolContext
) -> dict:
    """Put a figure from the student's textbook on their board.

    Use it when the book's own diagram says something your words cannot — a
    force diagram, a wave shape, the geometry of a projectile. Find it with
    search_textbook first; do not guess a page.

    **Pass `figure` whenever the student named one.** With it they get the
    diagram itself, cropped out of the page. Without it they get the entire
    printed page and have to hunt for the figure on it — which is exactly the
    complaint that led to this argument existing.

    Args:
        chapter: The chapter id from search_textbook, e.g. "keph103".
        page: The page within that chapter, from search_textbook.
        caption: One line saying what they should look at in it, in your words.
        figure: The figure number if there is one, e.g. "3.14". Pass "" only
            when the student asked for a whole page rather than a figure.

    Returns:
        dict with "block_id" and "showing", or {"error": ...}.
    """
    known = {c["file"]: c for c in _index()}
    ch = known.get(chapter)
    if ch is None:
        return {"error": f"no chapter {chapter!r}. Known: {sorted(known)}"}

    # A named figure carries its own page, and it beats the one passed in.
    # search_textbook can return several hits for one query, and the page that
    # merely MENTIONS a figure is an easy one to pick by mistake; the index
    # knows where the caption actually is.
    clip = None
    want = (figure or "").strip().lstrip("fig.Fig ").strip()
    if want:
        entry = next((f for f in ch["figures"] if f["figure"] == want), None)
        if entry is None:
            return {"error": f"{ch['title']} has no figure {want}. "
                             f"Known: {[f['figure'] for f in ch['figures']]}"}
        page = entry["page"]
        clip = entry.get("box")

    if not 1 <= int(page) <= ch["pages"]:
        return {"error": f"page {page} is outside {chapter} (1-{ch['pages']})"}

    session_id = tool_context.state.get("session_id") or "unknown"
    state = sessions.get(session_id)
    block = D.Pulled(
        id=state.mint("b_book"),
        label="From your textbook",
        source=f"Ch {ch['number']} · {ch['title']} · p.{page}",
        body=caption.strip(),
        figure=True,
        pdf=chapter,
        page=int(page),
        clip=clip,
    )
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        return {"error": str(exc)}
    log.info("textbook %s p.%s%s -> %s", chapter, page,
             f" fig {want} cropped" if clip else (f" fig {want} (whole page)" if want else ""),
             block.id)
    logs.count("textbook page")
    tool_context.state["textbook_search_streak"] = 0
    return {"block_id": block.id, "showing": block.source}


TEXTBOOK_TOOLS = [search_textbook, show_textbook_figure]
