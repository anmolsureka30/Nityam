/* The domain model.
 *
 * Shapes here deliberately mirror the sub-modules so the backend can be
 * plugged in without reshaping the UI:
 *   NotebookBlock  ~ sub_modules_examples/canvas/doc/schema.json
 *   ContextPacket  ~ sub_modules_examples/canvas/runtime/resolve.js
 *   ArtifactSpec   ~ sub_modules_examples/artifact_generator/ir/schema.json
 *   TutorState     ~ sub_modules_examples/adk (event.author, transcription, emotion)
 */

// ----------------------------------------------------------------- people

export interface Student {
  id: string;
  firstName: string;
  initial: string;
  klass: string;
}

export interface Teacher {
  id: string;
  displayName: string;
  klass: string;
}

// --------------------------------------------------------------- concepts

/** Mastery is 0-100. `delta` is the change from this session, if any. */
export interface Concept {
  id: string;
  name: string;
  mastery: number;
  delta?: number;
  /** What specifically goes wrong for this student. Written for them to read. */
  issue?: string;
  examinable?: boolean;
}

// ------------------------------------------------------------ class recap

export interface BoardCapture {
  id: string;
  at: string;
  label: string;
}

/** What the tutor knows about today's lesson, from audio plus board capture. */
export interface ClassRecap {
  subject: string;
  teacherName: string;
  date: string;
  startedAt: string;
  endedAt: string;
  captureCount: number;
  /** The question the teacher asked and never answered. The session's hook. */
  openQuestion: string;
  openQuestionContext: string;
  sources: BoardCapture[];
}

// ---------------------------------------------------------------- session

export type Intensity = "quick" | "standard" | "deep";

export interface IntensityOption {
  id: Intensity;
  label: string;
  minutes: number;
  promise: string;
  suggested?: boolean;
}

// ------------------------------------------------------- notebook content

/** An anchor is a span of a block the student can point at, and that the
 *  tutor can point at back. `concept` is what makes a gesture meaningful. */
export interface Anchor {
  id: string;
  /** Exact substring of the block's text. Must occur in it verbatim. */
  span: string;
  concept?: string;
}

export type NotebookBlock =
  | { kind: "heading"; id: string; text: string }
  | { kind: "tutor_text"; id: string; text: string; anchors?: Anchor[] }
  | { kind: "equation"; id: string; tex: string; caption?: string; anchors?: Anchor[] }
  | { kind: "callout"; id: string; tone: "correction" | "finding"; label: string; text: string }
  | { kind: "artifact"; id: string; artifactId: string }
  | { kind: "pulled"; id: string; label: string; source: string; body: string; quote?: string; figure?: boolean }
  | { kind: "next"; id: string; label: string; title: string; text: string };

export interface NotebookPage {
  page: number;
  eyebrow: string;
  blocks: NotebookBlock[];
}

export interface Notebook {
  id: string;
  conceptId: string;
  pages: NotebookPage[];
}

// -------------------------------------------------------------- grounding

export type MarkTool = "marker" | "circle" | "lasso";

/** One resolved thing the student pointed at. */
export interface ResolvedTarget {
  anchorId: string;
  text: string;
  concept?: string;
  /** 0-1. Below the floor a target is "nearby" rather than resolved. */
  coverage: number;
}

/** What the canvas hands the tutor when the student marks the page. This is
 *  the interface the real product plugs into. */
export interface ContextPacket {
  gesture: MarkTool | "text_selection";
  page: number;
  blockId: string | null;
  resolved: ResolvedTarget[];
  nearby: ResolvedTarget[];
  confidence: number;
  utterance?: string;
}

// --------------------------------------------------------------- artifact

/** Parameters of the one hand-written kernel this demo ships.
 *  In production the LLM emits the IR; the kernel stays hand-written. */
export interface ProjectileArtifact {
  id: string;
  title: string;
  eyebrow: string;
  speed: number;
  gravity: number;
  angle: number;
  angleMin: number;
  angleMax: number;
  /** Angles left on screen as dashed ghosts, so comparison is visible. */
  ghosts: number[];
}

// ------------------------------------------------------------ the tutor

export type TutorMood = "idle" | "listening" | "speaking" | "thinking" | "pleased";

export interface TutorState {
  /** Which agent is talking. Maps to ADK's `event.author`. */
  agent: "tutor" | "quiz_master";
  mood: TutorMood;
  caption: string;
  /** Set when a concept's mastery visibly moves. */
  masteryNote?: string;
}

// ------------------------------------------------------------- checkpoint

export interface CheckpointOption {
  id: string;
  letter: string;
  text: string;
  correct: boolean;
  /** Shown when this specific wrong answer is chosen — the misconception. */
  rebuttal?: string;
  tag?: string;
}

export interface Checkpoint {
  id: string;
  index: number;
  total: number;
  question: string;
  hint: string;
  options: CheckpointOption[];
  footnote: string;
}

// ---------------------------------------------------------------- summary

export interface SummaryMove {
  conceptName: string;
  from: number | null;
  to: number;
}

export interface SessionSummary {
  endedAt: string;
  minutes: number;
  headline: string;
  moved: SummaryMove[];
  moment: string;
  stillOpen: string;
  tomorrow: string;
}

// ---------------------------------------------------------------- teacher

export interface TaughtConcept {
  id: string;
  name: string;
  classMastery: number;
  trend: number;
  boardMinutes: number;
}

export interface AtRiskStudent {
  id: string;
  name: string;
  mastery: number;
  misconception: string;
  evidence: string;
  severity: "critical" | "watch" | "inactive";
}

export interface TeacherClassView {
  topic: string;
  meta: string;
  updatedAt: string;
  understanding: number;
  belowHalf: number;
  cohort: number;
  sharedMisconception: string;
  sharedMisconceptionCount: number;
  medianRevisionMin: number;
  concepts: TaughtConcept[];
  distribution: { band: string; count: number }[];
  didNotOpen: string[];
  beforeTheBell: string;
}
