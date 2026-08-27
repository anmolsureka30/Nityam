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

/** Every block can be struck through. Not a delete: a corrected mistake stays
 *  visible, because it teaches more than a mistake that quietly vanished.
 *  Written by the tutor's strike_block tool (backend/app/canvas/tools.py). */
interface BlockCommon {
  id: string;
  struck?: boolean;
}

export type NotebookBlock =
  | (BlockCommon & { kind: "heading"; text: string })
  | (BlockCommon & { kind: "tutor_text"; text: string; anchors?: Anchor[] })
  | (BlockCommon & { kind: "equation"; tex: string; caption?: string; anchors?: Anchor[] })
  | (BlockCommon & {
      kind: "callout";
      tone: "correction" | "finding";
      label: string;
      text: string;
    })
  | (BlockCommon & {
      kind: "artifact";
      artifactId: string;
      /** The validated Artifact IR, generated live by ArtifactAgent and carried
       *  inline in the patch. Absent for the hand-written fallback kernel. */
      ir?: unknown;
    })
  | (BlockCommon & {
      kind: "pulled";
      label: string;
      source: string;
      body: string;
      quote?: string;
      figure?: boolean;
    })
  | (BlockCommon & { kind: "next"; label: string; title: string; text: string });

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

/** One block the gesture touched, and what it swept from it.
 *
 *  There is deliberately only ONE kind of thing in a packet: text, plus the
 *  block it came from. An earlier version scored the authored `Anchor` spans
 *  and reported those instead, which meant a gesture across a whole sentence
 *  came back holding two letters — `v` and `θ` — and a gesture across
 *  unanchored prose came back empty. If an anchored term falls under the
 *  stroke it is now simply part of `text`, like every other word. */
export interface SweptRegion {
  blockId: string;
  kind: NotebookBlock["kind"];
  /** Verbatim: only the words this gesture actually covered in this block.
   *  `…` marks a gap where covered words were not adjacent. Empty for a block
   *  with no text of its own, such as the simulation. */
  text: string;
  /** The complete sentence(s) `text` sits inside, so the tutor gets coherent
   *  language even when the stroke started and ended mid-sentence. */
  sentences: string;
}

/** What the canvas hands the tutor when the student marks the page. This is
 *  the interface the real product plugs into. */
export interface ContextPacket {
  gesture: MarkTool;
  page: number;
  /** Every word the gesture covered, in document order, across all blocks. */
  text: string;
  /** One entry per block the gesture touched, in document order. */
  regions: SweptRegion[];
  /** The block that contributed the most swept text. */
  blockId: string | null;
  /** 1 when text was captured — a DOM-measured sweep is exact, not a guess —
   *  and 0 when the gesture landed on nothing. */
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
