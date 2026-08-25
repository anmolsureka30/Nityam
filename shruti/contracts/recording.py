from enum import Enum
from pydantic import BaseModel


class SurfaceKind(str, Enum):
    BLACKBOARD = "blackboard"
    WHITEBOARD = "whiteboard"
    SLIDES = "slides"
    MIXED = "mixed"
    TALKING_HEAD = "talking_head"


class Recording(BaseModel):
    id: str
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
