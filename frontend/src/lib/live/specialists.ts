/* Which specialist the tutor has delegated to, and what to say about it when
 * a specialist is working, named rather than generic.
 *
 * Kept as pure functions/data — no React, no hook state — so this is
 * testable exactly the same cheap way notebookReducer.ts already is: see
 * tests/specialists.mjs. useLiveSession.ts is the only caller that matters
 * for real; everything here is plain data transformation.
 */

export type Specialist = "board" | "artifact" | "quiz" | "textbook";

const SPECIALIST_BY_TOOL: Record<string, Specialist> = {
  ask_board: "board",
  ask_artifact: "artifact",
  ask_quiz: "quiz",
  ask_textbook: "textbook",
};

/** `null` for anything unrecognized. A future fifth delegate tool must fall
 *  back to the generic "thinking" copy, never throw and never leave the copy
 *  blank — this is the exact failure mode that broke the app once already,
 *  when the single `ask_tutor` tool these checks used to name was split into
 *  four and no branch matched anything (see useLiveSession.ts's own comment
 *  on this). */
export function resolveSpecialist(toolName: string | undefined): Specialist | null {
  if (!toolName) return null;
  return SPECIALIST_BY_TOOL[toolName] ?? null;
}

/** What the indicator says while a specialist works. Glyphs reuse the app's
 *  existing plain-geometric vocabulary rather
 *  than emoji, which would clash with this design system: `board` reuses the
 *  marker-tool glyph (SessionControls.tsx), `textbook` reuses the "View
 *  textbook" glyph (TextbookPeek.tsx). */
export const SPECIALIST_COPY: Record<Specialist, { glyph: string; verb: string }> = {
  board: { glyph: "✎", verb: "Sketching it on the board…" },
  artifact: { glyph: "▷", verb: "Building the simulation…" },
  quiz: { glyph: "?", verb: "Preparing a question…" },
  textbook: { glyph: "▦", verb: "Checking the textbook…" },
};

/** What the "she is thinking" indicator shows.
 *
 *  It used to prefer a `bridge` string the tutor passed as a tool argument —
 *  a sentence she was meant to be "saying" while the specialist worked, shown
 *  as text because it was never actually spoken. She speaks for herself
 *  throughout a delegation now, so her words belong in the bubble and this is
 *  a status line again: what is happening, not what she said. */
export function thinkingLine(specialist: Specialist | null): string {
  if (specialist) {
    const { glyph, verb } = SPECIALIST_COPY[specialist];
    return `${glyph} ${verb}`;
  }
  return "Looking that up for you…";
}
