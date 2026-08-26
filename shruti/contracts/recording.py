from enum import Enum
from pydantic import BaseModel


class SurfaceKind(str, Enum):
    BLACKBOARD = "blackboard"
    WHITEBOARD = "whiteboard"
    SLIDES = "slides"
    MIXED = "mixed"
    TALKING_HEAD = "talking_head"


def is_physical_board(surface_kind: "SurfaceKind | str") -> bool:
    """True only for the two surface kinds with an actual physical board to
    rectify, occlusion-mask, and gesture-track (blackboard/whiteboard).
    False for slides/mixed/talking_head, where GLYPH reads frames directly
    and there's nothing for PULSE's board-quad tracking or POINT's
    gesture-pointing to attach to — see
    memory_nityam_architecture/README.md's Phase 0.5 "Resolved" notes."""
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
