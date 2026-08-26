from typing import Literal
from pydantic import BaseModel


class LanguageSpan(BaseModel):
    start_s: float
    end_s: float
    lang: str


class Utterance(BaseModel):
    id: str
    recording_id: str
    start_s: float
    end_s: float
    text: str
    speaker: Literal["TEACHER", "STUDENT", "UNKNOWN"]
    language_spans: list[LanguageSpan] = []
    confidence: float | None = None


class Deixis(BaseModel):
    id: str
    recording_id: str
    at_s: float
    utterance_id: str | None = None
    phrase: str | None = None
    board_region: tuple[float, float, float, float]
    kind: Literal["point", "circle", "underline", "sweep", "write"]
    referent_text: str | None = None
    confidence: float | None = None
