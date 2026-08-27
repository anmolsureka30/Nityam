/* Applying the tutor's patches to the page.
 *
 * The backend owns the authoritative board (backend/app/sessions.py); this is
 * the local mirror the DOM renders. One writer, one reader — so a patch is
 * applied here exactly as it was applied there, and neither side reconciles.
 *
 * Pure and synchronous on purpose: it is the whole of what "the LLM writes on
 * the canvas" means, so it is testable without a browser, a socket or a model.
 */
import type { CanvasPatch, WireDoc } from "./live/protocol";
import type { Checkpoint, Notebook, NotebookBlock, NotebookPage } from "./types";

/** Alias kept so call sites read intentionally. `struck` and `ir` now live on
 *  NotebookBlock itself, since the backend really does send them. */
export type PageBlock = NotebookBlock;

export interface BoardState {
  doc: Notebook;
  /** Anchors the tutor is currently pointing at. Cleared by a TTL sweep, so
   *  "look at this" does not leave the page permanently lit up. */
  hot: Record<string, number>;
  /** Checkpoints queued by show_quiz. A 3-question quiz arrives as three
   *  patches in a row, so this is a queue, not a slot — otherwise questions 1
   *  and 2 flash past and only the last is ever answered. */
  quizQueue: Checkpoint[];
  /** Block the tutor asked to scroll to, consumed by the view. */
  scrollTo: string | null;
  /** Bumped on every applied patch, so effects can depend on "something
   *  changed" without deep-comparing the document. */
  revision: number;
}

export const emptyBoard = (id = "nb_local"): BoardState => ({
  doc: { id, conceptId: "", pages: [{ page: 1, eyebrow: "", blocks: [] }] },
  hot: {},
  quizQueue: [],
  scrollTo: null,
  revision: 0,
});

export function boardFromWire(wire: WireDoc): BoardState {
  return {
    ...emptyBoard(wire.id),
    doc: {
      id: wire.id,
      conceptId: wire.conceptId,
      pages: wire.pages.map((p) => ({
        page: p.page,
        eyebrow: p.eyebrow,
        blocks: p.blocks as NotebookBlock[],
      })),
    },
  };
}

export type BoardAction =
  | { type: "reset"; wire: WireDoc }
  | { type: "patch"; patch: CanvasPatch }
  | { type: "expire_hot"; now: number }
  | { type: "quiz_done" }
  | { type: "scrolled" };

function withPages(state: BoardState, pages: NotebookPage[]): BoardState {
  return { ...state, doc: { ...state.doc, pages }, revision: state.revision + 1 };
}

export function boardReducer(state: BoardState, action: BoardAction): BoardState {
  switch (action.type) {
    case "reset":
      return boardFromWire(action.wire);

    case "expire_hot": {
      const kept = Object.entries(state.hot).filter(([, until]) => until > action.now);
      if (kept.length === Object.keys(state.hot).length) return state;
      return { ...state, hot: Object.fromEntries(kept) };
    }

    case "quiz_done":
      return { ...state, quizQueue: state.quizQueue.slice(1) };

    case "scrolled":
      return state.scrollTo === null ? state : { ...state, scrollTo: null };

    case "patch":
      return applyPatch(state, action.patch);
  }
}

function applyPatch(state: BoardState, patch: CanvasPatch): BoardState {
  switch (patch.op) {
    case "append_block": {
      const target = patch.page ?? 1;
      // A patch can name a page that does not exist yet; the server does the
      // same thing (CanvasDoc.page creates on demand), so do not drop it.
      const exists = state.doc.pages.some((p) => p.page === target);
      const pages = exists
        ? state.doc.pages
        : [...state.doc.pages, { page: target, eyebrow: "", blocks: [] }].sort(
            (a, b) => a.page - b.page,
          );
      return withPages(
        state,
        pages.map((p) =>
          p.page === target
            ? { ...p, blocks: [...p.blocks, patch.block as NotebookBlock] }
            : p,
        ),
      );
    }

    case "replace_block":
      return withPages(
        state,
        state.doc.pages.map((p) => ({
          ...p,
          blocks: p.blocks.map((b) =>
            b.id === patch.blockId ? (patch.block as NotebookBlock) : b,
          ),
        })),
      );

    case "strike":
      return withPages(
        state,
        state.doc.pages.map((p) => ({
          ...p,
          blocks: p.blocks.map((b) => (b.id === patch.blockId ? { ...b, struck: true } : b)),
        })),
      );

    case "point_at": {
      const until = Date.now() + (patch.ttlMs || 9000);
      const hot = { ...state.hot };
      for (const id of patch.anchorIds) hot[id] = until;
      return { ...state, hot, revision: state.revision + 1 };
    }

    case "show_quiz":
      return {
        ...state,
        quizQueue: [...state.quizQueue, patch.checkpoint],
        revision: state.revision + 1,
      };

    case "goto":
      return { ...state, scrollTo: patch.blockId, revision: state.revision + 1 };
  }
}

