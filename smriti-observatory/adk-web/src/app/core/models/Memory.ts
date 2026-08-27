/**
 * @license
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * Mirrors the tutor app's SMRITI memory layer (app/memory/schemas.py,
 * app/memory/instrumentation.py) — the source of truth these types must
 * stay in sync with lives in that Python package, not here.
 */

export type Tier = 'workflow' | 'episodic' | 'long_term';
export type MemoryOperation = 'read' | 'write';
export type RecordType =
  | 'grounding_chunk'
  | 'dpm_profile'
  | 'teaching_memory'
  | 'session_log'
  | 'turn_buffer'
  | 'artifact_event';

export interface MemoryEvent {
  event_id: string;
  ts: string;
  session_id: string | null;
  student_id: string | null;
  tier: Tier;
  operation: MemoryOperation;
  record_type: RecordType;
  source_fn: string;
  trace_id: string | null;
  span_id: string | null;
  payload: unknown;
}

export interface FieldChange {
  path: string;
  kind: 'added' | 'removed' | 'changed';
  old: unknown;
  new: unknown;
  label: string;
}

export interface EnrichedMemoryEvent {
  event: MemoryEvent;
  diff: FieldChange[];
}

export interface MemoryTurn {
  turn: number;
  role: 'student' | 'tutor';
  text: string;
  concept_id: string | null;
  artifact_id: string | null;
}

export interface SessionLog {
  session_id: string;
  student_id: string;
  started_at: string;
  ended_at: string;
  turns: MemoryTurn[];
  summary: string;
}

export type Mastery = 'unknown' | 'misconceived' | 'partial' | 'known' | 'durable';
export type Strength = 'weak' | 'strong';

export interface Weakness {
  mastery: Mastery;
  strength: Strength;
  evidence: string[];
  last_updated: string | null;
}

export interface SelfReflection {
  note: string;
  helpful_count: number;
  harmful_count: number;
  evidence: string[];
  status: 'active' | 'superseded';
  superseded_by: string | null;
}

export interface DPMProfile {
  student_id: string;
  persona: {preferred_pace: string | null; language_mix: string | null; interests: string[]};
  weaknesses: Record<string, Weakness>;
  self_reflection: SelfReflection[];
}

export interface CoveredConcept {
  elements_used: string[];
  taught_at: string[];
  status: 'in_progress' | 'covered';
}

export interface OpenDoubt {
  concept_id: string;
  doubt: string;
  correct_understanding: string;
  status: 'active' | 'remediating' | 'resolved';
  evidence: string[];
}

export interface TeachingMemoryState {
  student_id: string;
  syllabus: string[];
  covered: Record<string, CoveredConcept>;
  open_doubts: OpenDoubt[];
  teaching_style: {current_mode: string; notes: string[]};
}

export interface MemorySessionState {
  session_id: string;
  student_id: string;
  workflow: {turn_buffer: MemoryTurn[]};
  episodic: {session_log: SessionLog | null};
  long_term: {
    dpm_profile: DPMProfile | null;
    teaching_memory: TeachingMemoryState | null;
  };
}
