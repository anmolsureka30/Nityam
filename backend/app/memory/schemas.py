"""Pydantic mirrors of the JSON Schemas in
project_documentation/memory_nityam_architecture/memory_layer.md §2.

These ARE the contract — every read/write against the memory store validates
against these classes, this isn't documentation of a separate format.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GroundingChunk(BaseModel):
    """One retrievable, citable unit of static knowledge. Never written by the
    tutor — only by Shruti ingestion or book ingestion."""

    chunk_id: str
    source_type: Literal["lecture", "book"]
    source_ref: str
    location: Optional[str] = None
    concept_ids: list[str] = Field(min_length=1)
    text: str


class Weakness(BaseModel):
    mastery: Literal["unknown", "misconceived", "partial", "known", "durable"]
    strength: Literal["weak", "strong"]
    evidence: list[str] = Field(min_length=1)
    last_updated: Optional[datetime] = None


class SelfReflection(BaseModel):
    """Tutor-authored pedagogical notes about this student — DeepTutor's D_r."""

    note: str
    helpful_count: int = 0
    harmful_count: int = 0
    evidence: list[str] = Field(min_length=1)
    status: Literal["active", "superseded"] = "active"
    superseded_by: Optional[str] = None


class Persona(BaseModel):
    preferred_pace: Optional[Literal["fast", "moderate", "deliberate"]] = None
    language_mix: Optional[str] = None
    interests: list[str] = Field(default_factory=list)


class DPMProfile(BaseModel):
    """Persona-level view: who am I teaching. Coarse per-concept mastery.
    Updated only via validated operations at session close — never rewritten
    wholesale (memory_layer.md §2.2, §4)."""

    student_id: str
    persona: Persona = Field(default_factory=Persona)
    weaknesses: dict[str, Weakness] = Field(default_factory=dict)
    self_reflection: list[SelfReflection] = Field(default_factory=list)


class CoveredConcept(BaseModel):
    elements_used: list[str] = Field(default_factory=list)
    taught_at: list[str] = Field(default_factory=list)
    status: Literal["in_progress", "covered"] = "in_progress"


class OpenDoubt(BaseModel):
    """The detailed record DPMProfile.weaknesses only flags a summary of."""

    concept_id: str
    doubt: str
    correct_understanding: str
    status: Literal["active", "remediating", "resolved"] = "active"
    evidence: list[str] = Field(min_length=1)


class TeachingStyle(BaseModel):
    current_mode: Literal["socratic", "worked-example", "guided-practice", "direct"] = "direct"
    notes: list[str] = Field(default_factory=list)


class TeachingMemory(BaseModel):
    """Operational view: what's the state of teaching them, right now
    (memory_layer.md §2.3)."""

    student_id: str
    syllabus: list[str] = Field(default_factory=list)
    covered: dict[str, CoveredConcept] = Field(default_factory=dict)
    open_doubts: list[OpenDoubt] = Field(default_factory=list)
    teaching_style: TeachingStyle = Field(default_factory=TeachingStyle)


class Turn(BaseModel):
    turn: int = Field(ge=1)
    role: Literal["student", "tutor"]
    text: str
    concept_id: Optional[str] = None
    artifact_id: Optional[str] = None


class SessionLog(BaseModel):
    """Episodic tier. Every DPM/TeachingMemory evidence pointer
    ('session_id#turn') resolves against a turn here (memory_layer.md §2.4)."""

    session_id: str
    student_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    turns: list[Turn] = Field(default_factory=list)
    summary: str = ""
