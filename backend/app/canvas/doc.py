"""The shared board: what the tutor writes and the student points at.

These models mirror `frontend/src/lib/types.ts` field for field, camelCase
included, so a patch is serialised straight onto the wire with no translation
layer between here and the reducer. If you add a block kind, add it in both
places or the frontend will silently skip it.

The one rule enforced here rather than trusted: **every anchor span must occur
verbatim in its own block's text.** An anchor whose span isn't in the text
renders as nothing, so the student can circle it all day and the tutor learns
nothing — a notebook that looks perfect and is useless. This is the referential
gate from sub_modules_examples/canvas/generate/validate.py, moved to the point
where a bad block cannot be constructed at all.
"""
from __future__ import annotations

import itertools
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

# ------------------------------------------------------------------ anchors


class Anchor(BaseModel):
    """A span of a block the student can point at, and the tutor can point back."""

    id: str
    span: str
    concept: str | None = None


def _check_anchors(text: str, anchors: list[Anchor], field: str) -> None:
    for a in anchors:
        if not a.span:
            raise ValueError(f"anchor {a.id!r} has an empty span")
        if a.span not in text:
            raise ValueError(
                f"anchor {a.id!r} spans {a.span!r}, which does not occur in the "
                f"block's {field}. The span must be copied out of the text "
                f"exactly, character for character."
            )


# ------------------------------------------------------------------- blocks


class _Block(BaseModel):
    id: str
    """Crossed out rather than deleted: a corrected mistake should stay visible."""
    struck: bool = False


class Heading(_Block):
    kind: Literal["heading"] = "heading"
    text: str


class TutorText(_Block):
    kind: Literal["tutor_text"] = "tutor_text"
    text: str
    anchors: list[Anchor] = Field(default_factory=list)

    @model_validator(mode="after")
    def _spans_present(self):
        _check_anchors(self.text, self.anchors, "text")
        return self


class Equation(_Block):
    kind: Literal["equation"] = "equation"
    tex: str
    caption: str | None = None
    anchors: list[Anchor] = Field(default_factory=list)

    @model_validator(mode="after")
    def _spans_present(self):
        _check_anchors(self.tex, self.anchors, "tex")
        return self


class Callout(_Block):
    kind: Literal["callout"] = "callout"
    tone: Literal["correction", "finding"]
    label: str
    text: str


class ArtifactBlock(_Block):
    kind: Literal["artifact"] = "artifact"
    artifactId: str
    """The validated IR, carried inline. The frontend mounts the artifact
    runtime against this — there is no HTML file and no URL to fetch."""
    ir: dict = Field(default_factory=dict)


class Pulled(_Block):
    kind: Literal["pulled"] = "pulled"
    label: str
    source: str
    body: str
    quote: str | None = None
    figure: bool = False
    """A clipped region of the textbook, as a data URL. Set when the student
    lassoed a diagram out of the PDF and it was rasterised in the browser."""
    image: str | None = None
    """Or: the chapter and page to render live, when the TUTOR asked for a
    figure rather than the student clipping one. The browser already has
    PDF.js and the file, so it renders the region itself — no server-side
    rasteriser, and no megabyte of base64 on the wire."""
    pdf: str | None = None
    page: int | None = None


class NextUp(_Block):
    kind: Literal["next"] = "next"
    label: str
    title: str
    text: str


Block = Annotated[
    Union[Heading, TutorText, Equation, Callout, ArtifactBlock, Pulled, NextUp],
    Field(discriminator="kind"),
]


def block_text(block: BaseModel) -> str:
    """The readable content of a block, for read_screen and for logging."""
    for field in ("text", "tex", "title", "body"):
        value = getattr(block, field, None)
        if value:
            return str(value)
    return ""


def block_anchors(block: BaseModel) -> list[Anchor]:
    return list(getattr(block, "anchors", []) or [])


# ------------------------------------------------------------------- quizzes


class CheckpointOption(BaseModel):
    id: str
    letter: str
    text: str
    correct: bool
    """Shown when this specific wrong answer is chosen — name the misconception."""
    rebuttal: str | None = None
    tag: str | None = None


class Checkpoint(BaseModel):
    id: str
    index: int = 1
    total: int = 1
    question: str
    hint: str = ""
    options: list[CheckpointOption]
    footnote: str = ""

    @model_validator(mode="after")
    def _exactly_one_right_answer(self):
        right = [o for o in self.options if o.correct]
        if len(right) != 1:
            raise ValueError(
                f"a checkpoint needs exactly one correct option, got {len(right)}"
            )
        return self


# -------------------------------------------------------------------- patches


class AppendBlock(BaseModel):
    op: Literal["append_block"] = "append_block"
    page: int = 1
    block: Block


class ReplaceBlock(BaseModel):
    op: Literal["replace_block"] = "replace_block"
    blockId: str
    block: Block


class Strike(BaseModel):
    op: Literal["strike"] = "strike"
    blockId: str


class PointAt(BaseModel):
    op: Literal["point_at"] = "point_at"
    anchorIds: list[str]
    ttlMs: int = 9000
    reason: str = ""


class ShowQuiz(BaseModel):
    op: Literal["show_quiz"] = "show_quiz"
    checkpoint: Checkpoint


class Goto(BaseModel):
    op: Literal["goto"] = "goto"
    blockId: str


Patch = Annotated[
    Union[AppendBlock, ReplaceBlock, Strike, PointAt, ShowQuiz, Goto],
    Field(discriminator="op"),
]


# --------------------------------------------------------------------- pages


class Page(BaseModel):
    page: int = 1
    eyebrow: str = ""
    blocks: list[Block] = Field(default_factory=list)


class CanvasDoc(BaseModel):
    id: str
    conceptId: str = ""
    pages: list[Page] = Field(default_factory=list)

    def page(self, number: int) -> Page:
        for p in self.pages:
            if p.page == number:
                return p
        created = Page(page=number)
        self.pages.append(created)
        self.pages.sort(key=lambda p: p.page)
        return created

    def blocks(self) -> list[BaseModel]:
        return [b for p in self.pages for b in p.blocks]

    def find(self, block_id: str):
        for block in self.blocks():
            if block.id == block_id:
                return block
        return None

    def anchor_ids(self) -> list[str]:
        return [a.id for b in self.blocks() for a in block_anchors(b)]


# ------------------------------------------------------------------ id minting

_slug_bad = re.compile(r"[^a-z0-9]+")


def slug(text: str, limit: int = 22) -> str:
    out = _slug_bad.sub("_", text.lower()).strip("_")
    return (out[:limit].rstrip("_")) or "x"


class IdMinter:
    """Block and anchor ids are minted here, never asked of the model.

    A model that invents its own ids drifts: it reuses one, or refers to a
    block it never created. Minting them server-side and handing them back in
    the tool result means `point_at` and `strike_block` can only ever name
    something that exists.
    """

    def __init__(self) -> None:
        self._counters: dict[str, itertools.count] = {}

    def next(self, prefix: str) -> str:
        counter = self._counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}_{next(counter)}"
