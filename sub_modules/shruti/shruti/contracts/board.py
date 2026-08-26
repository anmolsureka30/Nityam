from typing import Literal
from pydantic import BaseModel

RegionKind = Literal["equation", "text", "figure", "table", "diagram", "unreadable"]


class Region(BaseModel):
    id: str
    bbox: tuple[float, float, float, float]
    kind: RegionKind
    latex: str | None = None
    plain_text: str | None = None
    description: str | None = None
    role: str | None = None
    step_index: int | None = None
    # Informational, not an enforced reference (see migration 006) — GLYPH's
    # model naturally names descriptive derivation labels or multiple prior
    # steps, not always a single sibling region's literal id.
    derives_from: str | list[str] | None = None
    confidence: float | None = None
    reason: str | None = None


class BoardContent(BaseModel):
    regions: list[Region] = []


class BoardState(BaseModel):
    id: str
    recording_id: str
    idx: int
    valid_from_s: float
    valid_to_s: float
    composited_uri: str
    unfilled_uri: str | None = None
    ink_coverage: float | None = None
    ended_by: Literal["erase", "shot_cut", "end_of_video"]
    content: BoardContent | None = None
    ledger_version: int = 1
