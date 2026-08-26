from __future__ import annotations

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    concept_ids: list[str] = Field(min_length=1)
    text: str


class Turn(BaseModel):
    turn: int
    role: str
    text: str


class SessionLog(BaseModel):
    session_id: str
    student_id: str
    turns: list[Turn]


class Profile(BaseModel):
    student_id: str
    note: str
