/* The real student memory, fetched from backend/'s own read-only endpoints
 * (app/memory_routes.py) — the same store the tutor writes to at session
 * close. Nothing here is demo data: an empty response is a student who
 * hasn't had a session yet, not a bug, and every screen that reads this
 * must render that state honestly rather than fall back to lib/data.ts.
 *
 * Shapes mirror backend/app/memory/schemas.py exactly — that file is the
 * contract, this is its frontend mirror, the same relationship lib/types.ts
 * already has with the wire protocol.
 */
import { useEffect, useState } from "react";

export interface Persona {
  preferred_pace?: "fast" | "moderate" | "deliberate" | null;
  language_mix?: string | null;
  interests: string[];
}

export interface Weakness {
  mastery: "unknown" | "misconceived" | "partial" | "known" | "durable";
  strength: "weak" | "strong";
  evidence: string[];
  last_updated?: string | null;
}

export interface SelfReflection {
  note: string;
  helpful_count: number;
  harmful_count: number;
  evidence: string[];
  status: "active" | "superseded";
  superseded_by?: string | null;
}

export interface DPMProfile {
  student_id: string;
  persona: Persona;
  weaknesses: Record<string, Weakness>;
  self_reflection: SelfReflection[];
}

export interface OpenDoubt {
  concept_id: string;
  doubt: string;
  correct_understanding: string;
  status: "active" | "remediating" | "resolved";
  evidence: string[];
}

export interface TeachingStyle {
  current_mode: "socratic" | "worked-example" | "guided-practice" | "direct";
  notes: string[];
}

export interface TeachingMemory {
  student_id: string;
  syllabus: string[];
  covered: Record<string, { elements_used: string[]; taught_at: string[]; status: "in_progress" | "covered" }>;
  open_doubts: OpenDoubt[];
  teaching_style: TeachingStyle;
}

export interface SessionTurn {
  turn: number;
  role: "student" | "tutor";
  text: string;
  concept_id?: string | null;
  artifact_id?: string | null;
}

export interface SessionLog {
  session_id: string;
  student_id: string;
  started_at: string;
  ended_at?: string | null;
  turns: SessionTurn[];
  summary: string;
}

export interface StudentMemoryState {
  session_id: string;
  student_id: string;
  workflow: { turn_buffer: unknown };
  episodic: { session_log: SessionLog | null };
  long_term: { dpm_profile: DPMProfile | null; teaching_memory: TeachingMemory | null };
}

/** The real endpoint is per-session (`/sessions/{session_id}/state`), because
 *  its episodic half (session_log, turn_buffer) genuinely is session-scoped.
 *  Its long-term half — dpm_profile, teaching_memory, which is everything a
 *  profile view actually wants — is keyed purely by student_id server-side
 *  (backend/app/memory_routes.py:29-45: `store.get_dpm(db, student_id)` never
 *  touches session_id). So a profile view that isn't about one particular
 *  past session passes this fixed placeholder rather than inventing a fake
 *  session id: the server does an honest, harmless empty lookup for the
 *  episodic half (no session named "_profile" exists) and a real one for the
 *  long-term half, which is the only half this view reads. */
const PROFILE_PLACEHOLDER_SESSION = "_profile";

/** Thrown only for genuine transport/HTTP failures — a 200 with null profile
 *  fields is not an error, it's a student with no memory yet. */
export class MemoryFetchError extends Error {}

export async function fetchStudentMemory(studentId: string): Promise<StudentMemoryState> {
  const url = `/memory/sessions/${encodeURIComponent(PROFILE_PLACEHOLDER_SESSION)}/state`
    + `?student_id=${encodeURIComponent(studentId)}`;
  let res: Response;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new MemoryFetchError(`could not reach the memory service: ${(e as Error).message}`);
  }
  if (!res.ok) {
    throw new MemoryFetchError(`memory service returned ${res.status}`);
  }
  return (await res.json()) as StudentMemoryState;
}

export type MemoryLoadState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: StudentMemoryState };

/** Fetches once per `studentId` and exposes a tri-state the screen can render
 *  honestly from — loading, a real failure, or (possibly empty) real data.
 *  No caching beyond the component's lifetime: a profile view is exactly the
 *  kind of screen where "slightly stale" is the wrong trade against "just
 *  reloaded after the last session ended." */
export function useStudentMemory(studentId: string | undefined): MemoryLoadState {
  const [state, setState] = useState<MemoryLoadState>({ status: "loading" });

  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;
    setState({ status: "loading" });
    fetchStudentMemory(studentId)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((e: Error) => {
        if (!cancelled) setState({ status: "error", error: e.message });
      });
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  return state;
}

/** Mastery ordered worst-first, which is the order a student should act on
 *  it in — matches the reasoning HomeScreen already used for the demo data,
 *  now driven by whatever weaknesses the tutor has actually recorded. */
const MASTERY_SCORE: Record<Weakness["mastery"], number> = {
  unknown: 0,
  misconceived: 15,
  partial: 45,
  known: 75,
  durable: 95,
};

export function masteryPct(w: Weakness): number {
  return MASTERY_SCORE[w.mastery];
}

/* ─────────────────────────────────────────────── sessions and their recaps
 *
 * The memory layer's problem is not that it does not work — it is that it is
 * invisible. What a student (or a judge) can be shown is a list of the
 * sessions they have had and, inside each, what the tutor believed before and
 * what it believed after. These mirror backend/app/memory_routes.py. */

export interface SessionListItem {
  session_id: string;
  topic: string;
  mode: string;
  started_at: string | null;
  ended_at: string | null;
  summary: string;
  turns: number;
  changed: number;
  /** False for sessions that closed before recaps were recorded. The UI must
   *  say so rather than render an empty diff as "nothing changed". */
  has_recap: boolean;
}

export interface MasteryEntry {
  mastery: string;
  strength: string;
  evidence: string[];
}

export interface DoubtEntry {
  doubt: string;
  status: string;
  correct_understanding: string;
}

export interface MemoryChange {
  kind: "mastery" | "doubt";
  concept_id: string;
  from: string | null;
  to: string | null;
  strength?: string | null;
  doubt?: string;
}

export interface SessionRecap {
  found: boolean;
  session_id: string;
  topic: string;
  mode: string;
  started_at: string | null;
  ended_at: string | null;
  summary: string;
  turns: { turn: number; role: string; text: string }[];
  /** The finished notebook page, as the student left it. Null for sessions
   *  that closed before boards were stored. */
  board: { pages: { page: number; blocks: Record<string, unknown>[] }[] } | null;
  has_recap: boolean;
  before: { mastery: Record<string, MasteryEntry>; doubts: Record<string, DoubtEntry> };
  after: { mastery: Record<string, MasteryEntry>; doubts: Record<string, DoubtEntry> };
  changes: MemoryChange[];
  /** What Reflect proposed. `applied: false` is a rejected operation, and
   *  showing those is the point — it is the validation gate doing its job. */
  operations: { op: string; concept_id: string; args: Record<string, unknown>; applied: boolean }[];
}

export interface BriefingPreview {
  topic: string;
  mode: string;
  /** The steps shown across the top of the session screen, weakest first and
   *  the topic last. Derived from the same record the tutor is briefed on, so
   *  the header cannot promise a shape the lesson does not have. */
  plan: string[];
  concepts: string[];
  weak_points: { concept_id: string; mastery: string }[];
  open_doubts: { concept_id: string; doubt: string }[];
  last_session: string;
  covered: string[];
}

async function getJson<T>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new MemoryFetchError(`could not reach the memory service: ${(e as Error).message}`);
  }
  if (!res.ok) throw new MemoryFetchError(`memory service returned ${res.status}`);
  return (await res.json()) as T;
}

export function fetchSessions(studentId: string): Promise<{ sessions: SessionListItem[] }> {
  return getJson(`/memory/students/${encodeURIComponent(studentId)}/sessions`);
}

export function fetchSessionRecap(studentId: string, sessionId: string): Promise<SessionRecap> {
  return getJson(
    `/memory/students/${encodeURIComponent(studentId)}/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export function fetchBriefingPreview(
  studentId: string, conceptName: string, mode: string,
): Promise<BriefingPreview> {
  const q = new URLSearchParams({ conceptName, mode });
  return getJson(`/memory/students/${encodeURIComponent(studentId)}/briefing?${q}`);
}

/** How a mastery level should read and rank on screen. Ordered worst-first,
 *  because what a student needs to see is where they are stuck. */
export const MASTERY: Record<string, { label: string; rank: number }> = {
  misconceived: { label: "Misunderstood", rank: 0 },
  unknown: { label: "Not seen yet", rank: 1 },
  partial: { label: "Getting there", rank: 2 },
  known: { label: "Known", rank: 3 },
  durable: { label: "Solid", rank: 4 },
};

/** Did this change move the student forward? Used only for colour — a
 *  direction, not a score. */
export function movedForward(from: string | null, to: string | null): boolean {
  const a = MASTERY[from ?? ""]?.rank ?? -1;
  const b = MASTERY[to ?? ""]?.rank ?? -1;
  return b > a;
}
