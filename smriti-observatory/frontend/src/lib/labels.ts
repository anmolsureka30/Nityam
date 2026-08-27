import type { EnrichedEvent, MemoryEvent, RecordType, Tier } from "./types";

/** Standard, framework-agnostic memory-systems terminology — not SMRITI's
 * internal tier names. "workflow" -> Working Memory, "episodic" -> Episodic
 * Memory, "long_term" -> Long-Term Memory (further split below into its
 * real, distinct kinds: a learner profile, a teaching state, and a
 * knowledge-grounding index — these are different *kinds* of long-term
 * memory, not one blob, and showing them as one would be as unclear as
 * merging short-term and long-term memory into one box). */
export const TIER_LABEL: Record<Tier, string> = {
  workflow: "Working Memory",
  episodic: "Episodic Memory",
  long_term: "Long-Term Memory",
};

export const TIER_DESCRIPTION: Record<Tier, string> = {
  workflow: "The live turn buffer for this session — ephemeral, kept in-process and mirrored to Redis. Cleared once the session closes.",
  episodic: "The session's turn-by-turn record — written once, when the session closes. Every long-term claim cites back to a turn here.",
  long_term: "Persistent knowledge that outlives any one session — a learner profile, a teaching state, and a knowledge-grounding index.",
};

export const RECORD_TYPE_LABEL: Record<RecordType, string> = {
  turn_buffer: "Turn Buffer",
  artifact_event: "Artifact Event",
  session_log: "Session Log",
  dpm_profile: "Learner Profile",
  teaching_memory: "Teaching State",
  grounding_chunk: "Knowledge Grounding",
};

/** Which tier a record type is conceptually filed under, for the "State"
 * panel's grouping — long_term is split three ways there. */
export const RECORD_TYPE_GROUP: Record<RecordType, "workflow" | "episodic" | "dpm_profile" | "teaching_memory" | "grounding_chunk"> = {
  turn_buffer: "workflow",
  artifact_event: "workflow",
  session_log: "episodic",
  dpm_profile: "dpm_profile",
  teaching_memory: "teaching_memory",
  grounding_chunk: "grounding_chunk",
};

const SOURCE_FN_VERB: Record<string, string> = {
  append_turn: "Turn logged",
  append_artifact_event: "Artifact event logged",
  get_turn_buffer: "Turn buffer read",
  clear_session: "Turn buffer cleared",
  get_session_log: "Session log read",
  put_session_log: "Session log written",
  get_dpm: "Learner profile read",
  put_dpm: "Learner profile updated",
  get_teaching_memory: "Teaching state read",
  put_teaching_memory: "Teaching state updated",
  search_grounding: "Knowledge grounding searched",
  search_grounding_semantic: "Knowledge grounding searched (semantic)",
  put_grounding_chunk: "Knowledge chunk added",
};

function truncate(text: string, max = 72): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** One human-readable sentence describing what this event actually did —
 * the whole point being that a reader never has to parse JSON to know
 * what happened. */
export function describeEvent(event: MemoryEvent): string {
  const verb = SOURCE_FN_VERB[event.source_fn] ?? event.source_fn;
  const payload = event.payload as Record<string, unknown> | unknown[] | null;

  switch (event.source_fn) {
    case "append_turn": {
      const p = payload as { turn?: number; role?: string; text?: string } | null;
      if (p?.text) return `Turn ${p.turn} (${p.role}): "${truncate(p.text)}"`;
      return verb;
    }
    case "get_dpm":
    case "put_dpm": {
      const p = payload as { weaknesses?: Record<string, unknown> } | null;
      const n = p?.weaknesses ? Object.keys(p.weaknesses).length : 0;
      return `${verb} — ${n} tracked concept${n === 1 ? "" : "s"}`;
    }
    case "get_teaching_memory":
    case "put_teaching_memory": {
      const p = payload as { covered?: Record<string, unknown>; open_doubts?: unknown[] } | null;
      const covered = p?.covered ? Object.keys(p.covered).length : 0;
      const doubts = p?.open_doubts?.length ?? 0;
      return `${verb} — ${covered} concept${covered === 1 ? "" : "s"} covered, ${doubts} open doubt${doubts === 1 ? "" : "s"}`;
    }
    case "search_grounding":
    case "search_grounding_semantic": {
      const n = Array.isArray(payload) ? payload.length : 0;
      return `${verb} — ${n} chunk${n === 1 ? "" : "s"} found`;
    }
    case "get_session_log": {
      const p = payload as { turns?: unknown[] } | null;
      if (!p) return "Session log read — not written yet";
      return `${verb} — ${p.turns?.length ?? 0} turns`;
    }
    case "put_session_log": {
      const p = payload as { turns?: unknown[] } | null;
      return `${verb} — ${p?.turns?.length ?? 0} turns`;
    }
    default:
      return verb;
  }
}

export function eventKey(e: EnrichedEvent): string {
  return e.event.event_id;
}
