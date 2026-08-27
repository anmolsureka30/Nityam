/* The wire, in one file.
 *
 * Mirrors backend/app/canvas/doc.py and backend/app/main.py's read_client().
 * Field names are camelCase on both sides deliberately — a patch goes from a
 * pydantic model straight into the reducer with no translation step, so there
 * is nowhere for a rename to hide. If you add an op or a block kind, change it
 * here and in doc.py together.
 */
import type { Anchor, Checkpoint, NotebookBlock } from "../types";

// ------------------------------------------------------------- browser -> server

export type ClientMessage =
  | { type: "text"; text: string }
  | { type: "greet" }
  | { type: "gesture"; packet: unknown }
  | { type: "screen"; state: ScreenState }
  | { type: "artifact_evidence"; artifactId: string; event: string; detail?: string }
  | {
      type: "quiz_answer";
      checkpointId: string;
      optionId: string;
      optionText: string;
      correct: boolean;
    };

/** What the tutor sees when it calls read_screen. Sent on change, throttled —
 *  it is state, not conversation, so it never becomes a model turn by itself. */
export interface ScreenState {
  simulation?: Record<string, number>;
  quiz?: Record<string, unknown>;
  visibleBlockIds?: string[];
}

// ------------------------------------------------------------- server -> browser

/** Blocks arrive with `struck`, which the local type does not carry (nothing
 *  in the static demo data was ever struck). */
export type WireBlock = NotebookBlock & { struck?: boolean; ir?: unknown };

export type CanvasPatch =
  | { op: "append_block"; page: number; block: WireBlock }
  | { op: "replace_block"; blockId: string; block: WireBlock }
  | { op: "strike"; blockId: string }
  | { op: "point_at"; anchorIds: string[]; ttlMs: number; reason?: string }
  | { op: "show_quiz"; checkpoint: Checkpoint }
  | { op: "goto"; blockId: string };

export interface WireDoc {
  id: string;
  conceptId: string;
  pages: { page: number; eyebrow: string; blocks: WireBlock[] }[];
}

/** Our own frames, namespaced so they can never be mistaken for an ADK event. */
export type ControlFrame =
  | { kind: "session"; mode: string; model: string; board: WireDoc }
  | { kind: "canvas_patch"; patch: CanvasPatch }
  | { kind: "error"; message: string };

/** The shape of an ADK event, narrowed to the parts we actually read.
 *  ADK sends far more; anything not listed here is deliberately ignored. */
export interface AdkEvent {
  author?: string;
  partial?: boolean;
  interrupted?: boolean;
  turnComplete?: boolean;
  inputTranscription?: { text?: string };
  outputTranscription?: { text?: string };
  content?: {
    parts?: {
      text?: string;
      inlineData?: { mimeType?: string; data?: string };
      functionCall?: { name?: string; args?: Record<string, unknown> };
      functionResponse?: { name?: string; response?: Record<string, unknown> };
    }[];
  };
}

export type ServerFrame = ({ nityam?: never } & AdkEvent) | { nityam: ControlFrame };

export const isControl = (
  frame: ServerFrame,
): frame is { nityam: ControlFrame } => "nityam" in frame && !!frame.nityam;

export type { Anchor };
