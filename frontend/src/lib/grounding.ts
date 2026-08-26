/* Turning a gesture into meaning.
 *
 * Ported from sub_modules_examples/canvas/runtime/resolve.js, including the scoring fix
 * that module's tests caught: a marker swipe is judged by how much of an
 * anchor's *width* it sweeps, gated on vertical overlap. Scoring a swipe by
 * area silently dropped unambiguous highlights over tall content, which is the
 * worst possible failure — the student pointed at something and was ignored.
 */

import type { Anchor, ContextPacket, MarkTool, ResolvedTarget } from "./types";

/** Below this a target is reported as "nearby" rather than resolved, so a
 *  sloppy circle degrades into "probably this" instead of a wrong answer. */
export const RESOLVE_FLOOR = 0.35;
export const NEARBY_FLOOR = 0.05;

export interface Box { x: number; y: number; w: number; h: number }

export interface AnchorHit {
  anchor: Anchor;
  blockId: string;
  box: Box;
}

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
export function polygonCoverage(box: Box, poly: { x: number; y: number }[]): number {
  if (poly.length < 3) return 0;
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

function pointInPolygon(px: number, py: number, poly: { x: number; y: number }[]): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y;
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export function boundsOf(poly: { x: number; y: number }[]): Box {
  const xs = poly.map((p) => p.x);
  const ys = poly.map((p) => p.y);
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

/** The whole resolver: a gesture plus the anchor index becomes a packet the
 *  tutor can act on. Confidence is the best coverage, reported honestly. */
export function resolveGesture(
  tool: MarkTool,
  poly: { x: number; y: number }[],
  anchors: AnchorHit[],
  page: number,
): ContextPacket {
  const band = boundsOf(poly);
  const scored = anchors
    .map((hit) => ({
      hit,
      coverage:
        tool === "marker"
          ? markerCoverage(hit.box, band)
          : polygonCoverage(hit.box, poly),
    }))
    .filter((r) => r.coverage > NEARBY_FLOOR)
    .sort((a, b) => b.coverage - a.coverage);

  const toTarget = (r: { hit: AnchorHit; coverage: number }): ResolvedTarget => ({
    anchorId: r.hit.anchor.id,
    text: r.hit.anchor.span,
    concept: r.hit.anchor.concept,
    coverage: Math.round(r.coverage * 100) / 100,
  });

  const resolved = scored.filter((r) => r.coverage >= RESOLVE_FLOOR).map(toTarget);
  const nearby = scored.filter((r) => r.coverage < RESOLVE_FLOOR).map(toTarget);

  return {
    gesture: tool,
    page,
    blockId: scored[0]?.hit.blockId ?? null,
    resolved,
    nearby,
    confidence: resolved[0]?.coverage ?? 0,
  };
}

/** One line the student can read back, so the grounding is never a black box. */
export function describePacket(packet: ContextPacket): string {
  if (packet.resolved.length === 0) {
    return packet.nearby.length
      ? `Something near “${packet.nearby[0].text}” — not sure what.`
      : "A blank part of the page.";
  }
  const names = packet.resolved.map((r) => `“${r.text}”`);
  if (names.length === 1) return `You marked ${names[0]}.`;
  return `You marked ${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}.`;
}
