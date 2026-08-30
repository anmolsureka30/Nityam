"""Bridges a finished Shruti ingest run into Nityam's own memory store.

`scripts/seed_demo_data.py` used to be the only thing that ever turned a
`vault/wiki/<concept>.md` page into `grounding_chunk` rows — a script a
person had to remember to re-run by hand after every new recording. This
module is the same parsing logic, generalized so `shruti_routes.py` can call
it automatically the moment a live "paste a YouTube link" ingest finishes,
and points `current_topic` at whatever was just taught instead of leaving it
wherever it was last hand-seeded.

Deliberately does not touch Shruti's own storage (Postgres, the vault's
graph/embedding index) — see docs/superpowers/specs/
2026-08-28-cloud-memory-and-shruti-integration-design.md §1: that stays
exactly as Shruti's own 2026-08-26 design decided. This only reads the
already-written `vault/wiki/*.md` files Shruti produces and mirrors them into
Firestore/SQLite, same as the seed script always did.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.memory import store
from app.memory.schemas import CurrentTopic, GroundingChunk

log = logging.getLogger("nityam.shruti_sync")

_SECTION = re.compile(
    r"## Taught in (?P<source_ref>shruti:\S+) @(?P<location>[\d:]+)\n"
    r"(?P<body>.*?)(?=\n## Taught in|\Z)",
    re.DOTALL,
)


def parse_wiki_file(path: Path, subject: str = "projectile") -> list[GroundingChunk]:
    """One GroundingChunk per '## Taught in ...' section — each carries its
    own real citation (recording id + timestamp) straight from Shruti.

    `subject` namespaces the concept id (`"projectile.horizontal_range"`,
    matching what every existing agent/tool already expects — see
    memory/schemas.py's own concept_id convention). Defaults to "projectile"
    because that is every concept Shruti has ever ingested so far; a request
    that names a different subject (app/shruti_routes.py's IngestRequest
    already has the field) is not hardcoded out of this function's reach.
    """
    text = path.read_text()
    slug = path.stem
    concept_id = f"{subject}.{slug}" if subject else slug

    chunks = []
    for match in _SECTION.finditer(text):
        location = match.group("location")
        chunks.append(GroundingChunk(
            chunk_id=f"{slug}_{location.replace(':', '')}",
            source_type="lecture",
            source_ref=match.group("source_ref"),
            location=location,
            concept_ids=[concept_id],
            text=match.group("body").strip(),
        ))
    return chunks


def _humanize(slug: str) -> str:
    """'trajectory_equation_in_two-dimensional_motion' -> 'Trajectory
    equation in two-dimensional motion'. A readable fallback heading — not
    curated prose, just enough that the dashboard never shows a raw slug."""
    words = slug.replace("_", " ").replace("-", " ")
    return words[:1].upper() + words[1:] if words else slug


def sync_ingested_recording(
    wiki_dir: Path,
    recording_slug: str,
    concept_ids: list[str],
    student_id: str,
    subject: str = "projectile",
    video_title: str = "",
    youtube_url: str = "",
) -> int:
    """Call once a `shruti ingest` run has finished. Writes every touched
    concept's wiki content into grounding_chunks (shared, citable knowledge —
    not owned by whoever uploaded it), then points `current_topic` at the
    first one for `student_id` specifically — so it's the uploader's own
    next session that opens on what they just uploaded, not every student's.

    Returns how many grounding chunks were written (0 if nothing matched,
    e.g. the wiki files aren't reachable from this process — a real
    possibility once Shruti and Nityam stop being co-located, at which point
    this function's caller becomes the thing to change, not this one).
    """
    if not concept_ids:
        return 0

    conn = store.connect()
    written = 0
    for slug in concept_ids:
        path = wiki_dir / f"{slug}.md"
        if not path.exists():
            log.warning("shruti_sync: wiki page missing for concept %r (%s)", slug, path)
            continue
        for chunk in parse_wiki_file(path, subject=subject):
            store.put_grounding_chunk(conn, chunk)
            written += 1

    if written:
        first_slug = concept_ids[0]
        concept_id = f"{subject}.{first_slug}" if subject else first_slug
        topic = CurrentTopic(
            student_id=student_id,
            concept_id=concept_id,
            heading=_humanize(first_slug),
            eyebrow=f"From class · {video_title}" if video_title else "From your last upload",
            subject=subject,
            recording_slug=recording_slug,
            video_title=video_title,
            youtube_url=youtube_url,
            updated_at=datetime.now(timezone.utc),
        )
        # Both the active pointer (what the next session opens on) and this
        # student's full upload history (what the dashboard's "study this
        # instead" picker lists) — a fresh upload becomes the active one, but
        # nothing already ingested is lost or overwritten.
        store.put_current_topic(conn, topic)
        store.add_topic_history(conn, topic)
        log.info(
            "shruti_sync: wrote %d grounding chunk(s) for recording %r, current_topic[%s] -> %r",
            written, recording_slug, student_id, concept_id,
        )
    return written
