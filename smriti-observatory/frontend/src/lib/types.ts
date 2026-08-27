export type Tier = "workflow" | "episodic" | "long_term";
export type Operation = "read" | "write";
export type RecordType =
  | "grounding_chunk"
  | "dpm_profile"
  | "teaching_memory"
  | "session_log"
  | "turn_buffer"
  | "artifact_event";

export interface MemoryEvent {
  event_id: string;
  ts: string;
  session_id: string | null;
  student_id: string | null;
  tier: Tier;
  operation: Operation;
  record_type: RecordType;
  source_fn: string;
  trace_id: string | null;
  span_id: string | null;
  payload: unknown;
}

export interface FieldChange {
  path: string;
  kind: "added" | "removed" | "changed";
  old: unknown;
  new: unknown;
  label: string;
}

export interface EnrichedEvent {
  event: MemoryEvent;
  diff: FieldChange[];
}

export interface Turn {
  turn: number;
  role: "student" | "tutor";
  text: string;
  concept_id: string | null;
  artifact_id: string | null;
}

export interface SessionLog {
  session_id: string;
  student_id: string;
  started_at: string;
  ended_at: string;
  turns: Turn[];
  summary: string;
}

export type Mastery = "unknown" | "misconceived" | "partial" | "known" | "durable";
export type Strength = "weak" | "strong";

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
  status: "active" | "superseded";
  superseded_by: string | null;
}

export interface DPMProfile {
  student_id: string;
  persona: { preferred_pace: string | null; language_mix: string | null; interests: string[] };
  weaknesses: Record<string, Weakness>;
  self_reflection: SelfReflection[];
}

export interface CoveredConcept {
  elements_used: string[];
  taught_at: string[];
  status: "in_progress" | "covered";
}

export interface OpenDoubt {
  concept_id: string;
  doubt: string;
  correct_understanding: string;
  status: "active" | "remediating" | "resolved";
  evidence: string[];
}

export interface TeachingMemoryState {
  student_id: string;
  syllabus: string[];
  covered: Record<string, CoveredConcept>;
  open_doubts: OpenDoubt[];
  teaching_style: { current_mode: string; notes: string[] };
}

export interface SessionState {
  session_id: string;
  student_id: string;
  workflow: { turn_buffer: Turn[] };
  episodic: { session_log: SessionLog | null };
  long_term: {
    dpm_profile: DPMProfile | null;
    teaching_memory: TeachingMemoryState | null;
  };
}
