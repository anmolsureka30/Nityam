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

import json
import logging
from pathlib import Path

from google.adk.tools import ToolContext

from app import logs, sessions
from app.canvas import doc as D

log = logging.getLogger("nityam.textbook")

INDEX_PATH = Path(__file__).resolve().parent / "textbook_index.json"


def _index() -> list[dict]:
    try:
        return json.loads(INDEX_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        log.warning("no textbook index at %s", INDEX_PATH)
        return []


def search_textbook(query: str) -> dict:
    """Find where something is covered in the student's own NCERT textbook.

    Search the section headings and figure numbers of the four Class XI Physics
    chapters that are loaded. Use it before claiming the book says anything, and
    to find the page a figure is on so you can put it on their board.

    Args:
        query: A topic, section title or figure number — "projectile",
            "friction", "13.3", "Fig 3.14".

    Returns:
        dict with "hits": chapters, sections and figures that match, each with
        the `chapter` id and `page` that show_textbook_figure needs.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"hits": [], "note": "give me something to look for"}

    hits: list[dict] = []
    for ch in _index():
        label = f"Ch {ch['number']} · {ch['title']}"
        if q in ch["title"].lower():
            hits.append({"kind": "chapter", "chapter": ch["file"], "title": label, "page": 1})
        for sec in ch["sections"]:
            if q in sec["title"].lower() or q == sec["section"]:
                hits.append({
                    "kind": "section", "chapter": ch["file"], "page": sec["page"],
                    "title": f"{sec['section']} {sec['title'].title()}", "in": label,
                })
        for pg in ch.get("pageText", []):
            if q in pg["words"]:
                hits.append({
                    "kind": "page", "chapter": ch["file"], "page": pg["page"],
                    "title": f"{label}, page {pg['page']} mentions “{query.strip()}”",
                    "in": label,
                })
        for fig in ch["figures"]:
            if q.replace("fig.", "").replace("fig", "").strip() == fig["figure"]:
                hits.append({
                    "kind": "figure", "chapter": ch["file"], "page": fig["page"],
                    "title": f"Fig. {fig['figure']}", "in": label,
                })
    return {"hits": hits[:12], "found": len(hits)}


def show_textbook_figure(
    chapter: str, page: int, caption: str, tool_context: ToolContext
) -> dict:
    """Put a page of the student's textbook on their board, next to your work.

    Use it when the book's own diagram says something your words cannot — a
    force diagram, a wave shape, the geometry of a projectile. Find the page
    with search_textbook first; do not guess one.

    Args:
        chapter: The chapter id from search_textbook, e.g. "keph103".
        page: The page within that chapter, from search_textbook.
        caption: One line saying what they should look at in it, in your words.

    Returns:
        dict with "block_id", or {"error": ...} if that page does not exist.
    """
    known = {c["file"]: c for c in _index()}
    ch = known.get(chapter)
    if ch is None:
        return {"error": f"no chapter {chapter!r}. Known: {sorted(known)}"}
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
    )
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        return {"error": str(exc)}
    log.info("textbook %s p.%s -> %s", chapter, page, block.id)
    logs.count("textbook page")
    # So the voice layer can say which page it is and answer "is this in the
    # book?" without a round trip.
    sessions.inject(
        session_id,
        f"[BOARD UPDATED, context only — do not announce it or reply to this. "
        f"A page of the student's own NCERT textbook is now on their page as "
        f"{block.id}: {block.source}. You said about it: “{block.body}”. "
        f"You may refer to it and answer questions about which page it is "
        f"yourself.]",
    )
    return {"block_id": block.id, "showing": block.source}


TEXTBOOK_TOOLS = [search_textbook, show_textbook_figure]
