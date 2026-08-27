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

export interface SessionState {
  session_id: string;
  student_id: string;
  workflow: { turn_buffer: Record<string, unknown>[] };
  episodic: { session_log: Record<string, unknown> | null };
  long_term: {
    dpm_profile: Record<string, unknown> | null;
    teaching_memory: Record<string, unknown> | null;
  };
}
