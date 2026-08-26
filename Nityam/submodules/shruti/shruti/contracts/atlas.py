from typing import Literal
from pydantic import BaseModel

EdgeType = Literal["REQUIRES", "PART_OF", "EXEMPLIFIES", "CONTRASTS_WITH"]


class BeatRef(BaseModel):
    beat_id: str
    relation: Literal["taught_in", "mentioned_in", "evidence_for"]


class Concept(BaseModel):
    id: str
    canonical_name: str
    aliases: list[str] = []
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None
    definition: str | None = None
    atlas_version: int = 1
    taught_in: list[BeatRef] = []


class Edge(BaseModel):
    id: str
    from_concept: str
    to_concept: str
    edge_type: EdgeType
    weight: float = 1.0
    atlas_version: int = 1
    evidence: list[BeatRef] = []


class Misconception(BaseModel):
    id: str
    concept_id: str
    statement: str
    teacher_phrasing: str | None = None
    correct_understanding: str
    pre_empted_at_beat: str
    board_region_id: str | None = None
    atlas_version: int = 1
