/* Which specialist the tutor has delegated to, and what to say about it when
 * she has not given her own bridge line.
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
 *  four and no branch matched anything (see useLiveSession.ts own comment
 *  on this). */
export function resolveSpecialist(toolName: string | undefined): Specialist | null {
  if (!toolName) return null;
  return SPECIALIST_BY_TOOL[toolName] ?? null;
}

/** Fallback phrase, shown only when the tutor has not supplied her own bridge
 *  line. Glyphs reuse the app existing plain-geometric vocabulary rather
 *  than emoji, which would clash with this design system: `board` reuses the
 *  marker-tool glyph (SessionControls.tsx), `textbook` reuses the "View
 *  textbook" glyph (TextbookPeek.tsx). */
export const SPECIALIST_COPY: Record<Specialist, { glyph: string; verb: string }> = {
  board: { glyph: "✎", verb: "Sketching it on the board…" },
  artifact: { glyph: "▷", verb: "Building the simulation…" },
  quiz: { glyph: "?", verb: "Preparing a question…" },
  textbook: { glyph: "▦", verb: "Checking the textbook…" },
};

/** What the "she is thinking" indicator shows. Her own words always win when
 *  present; the specialist-specific phrase is only the fallback for when they
 *  aren't. */
export function thinkingLine(
  bridge: string | undefined,
  specialist: Specialist | null,
): string {
  const line = bridge?.trim();
  if (line) return line;
  if (specialist) {
    const { glyph, verb } = SPECIALIST_COPY[specialist];
    return `${glyph} ${verb}`;
  }
  return "Looking that up for you…";
}
