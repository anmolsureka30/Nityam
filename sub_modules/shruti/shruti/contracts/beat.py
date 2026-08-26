from typing import Literal
from pydantic import BaseModel
from shruti.contracts.speech import Utterance, Deixis

BeatKind = Literal["explain", "derive", "example", "question", "recap", "aside", "admin"]


class Beat(BaseModel):
    id: str
    recording_id: str
    idx: int
    start_s: float
    end_s: float
    kind: BeatKind
    speech: list[Utterance] = []
    board_state_id: str | None = None
    board_delta: tuple[float, float, float, float] | None = None
    deixis: list[Deixis] = []
    concepts: list[str] = []
    salience: float | None = None
    transcript: str
