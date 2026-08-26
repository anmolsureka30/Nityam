from enum import Enum
from pydantic import BaseModel


class SurfaceKind(str, Enum):
    BLACKBOARD = "blackboard"
    WHITEBOARD = "whiteboard"
    SLIDES = "slides"
    MIXED = "mixed"
    TALKING_HEAD = "talking_head"


def is_physical_board(surface_kind: "SurfaceKind | str") -> bool:
    """True only for recordings classified as board-only for their entire
    duration (blackboard/whiteboard) — where board-quad rectification,
    occlusion masking, and gesture-pointing all apply throughout. False for
    slides/talking_head, which genuinely have no physical board anywhere,
    AND for mixed — which does contain a real board, but not for the whole
    recording, and this pipeline classifies surface_kind once per recording
    with no per-segment routing yet. Treating mixed as non-board here avoids
    incorrectly running full-video board rectification against segments
    that are actually slides; it also means PULSE's board-quad tracking and
    POINT's gesture-pointing are skipped entirely for mixed recordings today
    — a real, open gap (see memory_nityam_architecture/README.md's Phase
    0.5 notes for both this and the surface_kind branching this predicate
    was built for)."""
    value = surface_kind.value if isinstance(surface_kind, SurfaceKind) else surface_kind
    return value in ("blackboard", "whiteboard")


class Recording(BaseModel):
    id: str
    slug: str | None = None
    source_uri: str
    title: str | None = None
    duration_s: float
    fps: float
    width: int | None = None
    height: int | None = None
    surface_kind: SurfaceKind
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None
    reel_version: int = 1
