/* Turning a gesture into meaning.
 *
 * The geometry is ported from sub_modules_examples/canvas/runtime/resolve.js,
 * including the scoring fix that module's tests caught: a marker swipe is
 * judged by how much of a box's *width* it sweeps, gated on vertical overlap.
 * Scoring a swipe by area silently dropped unambiguous highlights over tall
 * content, which is the worst possible failure — the student pointed at
 * something and was ignored.
 *
 * What the geometry is applied TO has changed. That module scored the authored
 * anchor spans, so a gesture could only ever come back holding one of them; in
 * this notebook that meant three tokens (`v`, `θ`, `sin(2θ)`) on a page of
 * prose, and a sweep across anything else resolved to nothing at all. Here the
 * same functions score individual WORDS, so a gesture reports the text it
 * actually covered and the block it came from. Anchors still exist, but only as
 * the tutor's half of two-way pointing — she lights one up while she talks
 * about it, via the `hot` map — not as the thing a gesture resolves to.
 *
 * Everything in this file is pure. The DOM half lives in
 * features/session/readPage.ts, which is what feeds `buildPacket`.
 */

import type { ContextPacket, MarkTool, NotebookBlock, SweptRegion } from "./types";

/** A word counts as swept once the gesture covers this much of it.
 *  Deliberately inclusive: a half-covered word at the start of a swipe was
 *  meant, and dropping it would hand the tutor a sentence missing its subject. */
export const SWEPT_FLOOR = 0.35;

/** How much of the swept text the one-line summary shows before eliding. */
export const SUMMARY_MAX = 90;

export interface Box { x: number; y: number; w: number; h: number }
export interface Point { x: number; y: number }

const overlap1d = (a0: number, a1: number, b0: number, b1: number) =>
  Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));

/** How much of `box` a marker stroke swept, by width, gated on vertical overlap. */
export function markerCoverage(box: Box, band: Box): number {
  const vo = overlap1d(box.y, box.y + box.h, band.y, band.y + band.h);
  if (vo <= 0 || box.w <= 0) return 0;
  const vFactor = Math.min(1, vo / Math.max(1, Math.min(band.h, box.h)));
  const ho = overlap1d(box.x, box.x + box.w, band.x, band.x + band.w);
  return (ho / box.w) * vFactor;
}

/** Fraction of `box` inside a polygon, by sampling a 6×6 grid. */
export function polygonCoverage(box: Box, poly: Point[]): number {
  if (poly.length < 3 || box.w <= 0 || box.h <= 0) return 0;
  const N = 6;
  let inside = 0;
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const px = box.x + (box.w * (i + 0.5)) / N;
      const py = box.y + (box.h * (j + 0.5)) / N;
      if (pointInPolygon(px, py, poly)) inside++;
    }
  }
  return inside / (N * N);
}

function pointInPolygon(px: number, py: number, poly: Point[]): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y;
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export function boundsOf(poly: Point[]): Box {
  const xs = poly.map((p) => p.x);
  const ys = poly.map((p) => p.y);
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

/** The one place that decides how a tool is scored, so no two callers can
 *  disagree about what "covered" means for a marker versus a loop. */
export function coverageOf(tool: MarkTool, box: Box, poly: Point[], band: Box): number {
  return tool === "marker" ? markerCoverage(box, band) : polygonCoverage(box, poly);
}

/** Does a box overlap the gesture's bounding band at all? Used both as a cheap
 *  reject before per-word measurement, and as the only available test for a
 *  block with no words in it. */
export function intersects(box: Box, band: Box): boolean {
  return (
    overlap1d(box.x, box.x + box.w, band.x, band.x + band.w) > 0 &&
    overlap1d(box.y, box.y + box.h, band.y, band.y + band.h) > 0
  );
}

// ------------------------------------------------------------ swept text

const TERMINAL = /[.;?!]["'”’)]?$/;

/** The words a gesture covered, plus the sentences they sit in.
 *
 *  `words` is every word in the block in document order; `kept` is the indices
 *  the gesture covered. Two things this is careful about:
 *
 *  - A gap between kept words becomes `…`. A lasso can cover the ends of a line
 *    and miss its middle, and joining across that with a space would hand the
 *    tutor a sentence the student never highlighted.
 *  - `sentences` widens to whole sentences, because a stroke almost always
 *    starts and ends mid-sentence and a fragment is poor material to reason
 *    about. It never narrows: text with no terminator (an equation, a heading)
 *    is one sentence, which is the right answer for both.
 */
export function groupSweptText(words: string[], kept: number[]): { text: string; sentences: string } {
  const hit = new Set(kept);
  if (hit.size === 0) return { text: "", sentences: "" };

  const ordered = [...hit].sort((a, b) => a - b);

  let text = "";
  let prev = -1;
  for (const i of ordered) {
    if (prev >= 0) text += i === prev + 1 ? " " : " … ";
    text += words[i];
    prev = i;
  }

  /* Sentence bounds are derived from the word list rather than re-split from a
     joined string, so word indices and sentence membership cannot drift. */
  const sentences: string[] = [];
  let current: string[] = [];
  let currentHit = false;
  for (let i = 0; i < words.length; i++) {
    current.push(words[i]);
    if (hit.has(i)) currentHit = true;
    if (TERMINAL.test(words[i]) || i === words.length - 1) {
      if (currentHit) sentences.push(current.join(" "));
      current = [];
      currentHit = false;
    }
  }

  return { text, sentences: sentences.join(" ") };
}

// --------------------------------------------------------------- the packet

/** Assemble the packet the tutor acts on. The measuring is already done by the
 *  time this is called — see features/session/readPage.ts. */
export function buildPacket(tool: MarkTool, page: number, regions: SweptRegion[]): ContextPacket {
  const withText = regions.filter((r) => r.text.length > 0);

  /* The dominant block is the one that gave up the most text, not the first
     one touched: clipping the tail of a paragraph on the way into an equation
     should not make the paragraph the subject. */
  const dominant = withText.reduce<SweptRegion | null>(
    (best, r) => (best === null || r.text.length > best.text.length ? r : best),
    null,
  );

  return {
    gesture: tool,
    page,
    text: withText.map((r) => r.text).join(" "),
    regions,
    blockId: dominant?.blockId ?? regions[0]?.blockId ?? null,
    confidence: withText.length > 0 ? 1 : 0,
  };
}

// ------------------------------------------------------------- description

/** What a block is, said the way a student would say it. */
const SOURCE: Record<NotebookBlock["kind"], string> = {
  heading: "your notes",
  tutor_text: "your notes",
  equation: "the equation",
  callout: "your notes",
  artifact: "the simulation",
  pulled: "the textbook note",
  next: "what's next",
};

const elide = (s: string) =>
  s.length <= SUMMARY_MAX ? s : `${s.slice(0, SUMMARY_MAX - 1).trimEnd()}…`;

/** One line the student can read back, so the grounding is never a black box. */
export function describePacket(packet: ContextPacket): string {
  if (packet.text) return `You marked “${elide(packet.text)}”.`;
  const region = packet.regions[0];
  if (region) return `You marked ${SOURCE[region.kind]}.`;
  return "A blank part of the page.";
}

/** Where it came from, for the small line under the summary. Names every
 *  distinct source once, in the order the gesture crossed them. */
export function describeSource(packet: ContextPacket): string {
  return [...new Set(packet.regions.map((r) => SOURCE[r.kind]))].join(" · ");
}
