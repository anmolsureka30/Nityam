"""Seed one demo student against real, already-ingested projectile-motion
content from sub_modules_examples/shruti/vault/wiki/ — not invented text
(architecture.md, "Demo subject" decision).

Run directly: `uv run python scripts/seed_demo_data.py`
"""
from __future__ import annotations

import re
from pathlib import Path

from app.memory import store
from app.memory.schemas import DPMProfile, GroundingChunk, Persona, TeachingMemory

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# Shruti lives under sub_modules_examples/, a sibling of sub_modules/ at the
# repo root (renamed upstream from sub_modules/shruti/; tutor stayed put).
WIKI_DIR = REPO_ROOT / "sub_modules_examples" / "shruti" / "vault" / "wiki"

_SECTION = re.compile(
    r"## Taught in (?P<source_ref>shruti:\S+) @(?P<location>[\d:]+)\n"
    r"(?P<body>.*?)(?=\n## Taught in|\Z)",
    re.DOTALL,
)


def parse_wiki_file(path: Path) -> list[GroundingChunk]:
    """One GroundingChunk per '## Taught in ...' section — each carries its
    own real citation (recording id + timestamp) straight from Shruti."""
    text = path.read_text()
    slug = path.stem
    concept_id = f"projectile.{slug}"

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


def seed(conn) -> None:
    concept_ids = []
    for wiki_file in sorted(WIKI_DIR.glob("*.md")):
        chunks = parse_wiki_file(wiki_file)
        for chunk in chunks:
            store.put_grounding_chunk(conn, chunk)
        if chunks:
            concept_ids.append(chunks[0].concept_ids[0])

    store.put_dpm(conn, DPMProfile(
        student_id="demo_student",
        persona=Persona(preferred_pace="moderate", language_mix="en", interests=["cricket"]),
    ))
    store.put_teaching_memory(conn, TeachingMemory(
        student_id="demo_student",
        syllabus=concept_ids,
    ))


if __name__ == "__main__":
    conn = store.connect()
    seed(conn)
    print(f"Seeded demo_student against {WIKI_DIR}")
