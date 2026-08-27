import { useRef, useState } from "react";
import { boundsOf, buildPacket } from "../../lib/grounding";
import type { Point } from "../../lib/grounding";
import type { ContextPacket, MarkTool } from "../../lib/types";
import { readSweptRegions } from "./readPage";
import s from "./AnnotationLayer.module.css";

/* Half the drawn nib height. A marker stroke is a horizontal drag, so its raw
 * bounds are a zero-height line and every vertical-overlap test scores zero —
 * the student highlights a word and is told "not sure what you marked". The
 * band has to be as thick as the nib they can see. */
const NIB = 9;

export interface Stroke {
  id: string;
  tool: MarkTool;
  points: Point[];
}

export default function AnnotationLayer({
  hostRef, tool, strokes, onStroke, onPacket,
}: {
  hostRef: React.RefObject<HTMLDivElement | null>;
  tool: MarkTool | null;
  strokes: Stroke[];
  onStroke: (stroke: Stroke) => void;
  onPacket: (packet: ContextPacket) => void;
}) {
  const [live, setLive] = useState<Point[]>([]);
  const drawing = useRef(false);

  function toLocal(e: React.PointerEvent): Point {
    const host = hostRef.current!;
    const r = host.getBoundingClientRect();
    return {
      x: e.clientX - r.left + host.scrollLeft,
      y: e.clientY - r.top + host.scrollTop,
    };
  }

  function down(e: React.PointerEvent) {
    if (!tool) return;
    drawing.current = true;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setLive([toLocal(e)]);
  }

  function move(e: React.PointerEvent) {
    if (!drawing.current || !tool) return;
    const p = toLocal(e);
    // Thin the path: a pointer fires far more often than a gesture changes
    // shape, and every extra point costs a polygon test later.
    setLive((prev) => {
      const last = prev[prev.length - 1];
      if (last && Math.hypot(p.x - last.x, p.y - last.y) < 3) return prev;
      return [...prev, p];
    });
  }

  function up() {
    if (!drawing.current || !tool) return;
    drawing.current = false;
    const points = live;
    setLive([]);
    // A tap is not a gesture. Two points is a slip of the hand.
    if (points.length < 3) return;

    const stroke: Stroke = { id: `st_${Date.now()}`, tool, points };
    onStroke(stroke);

    const host = hostRef.current;
    if (!host) return;
    const shape = gestureShape(tool, points);
    onPacket(buildPacket(tool, pageUnder(host, points), readSweptRegions(host, tool, shape)));
  }

  const armed = tool !== null;

  return (
    <div
      className={`${s.layer} ${armed ? s.armed : s.inert}`}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
    >
      <svg className={s.svg} aria-hidden="true">
        {strokes.map((st) => (
          <Mark key={st.id} stroke={st} />
        ))}
        {live.length > 1 && tool && <Mark stroke={{ id: "live", tool, points: live }} live />}
      </svg>
    </div>
  );
}

/** Which page the gesture actually landed on.
 *
 *  This used to be a prop, and the only caller passed the FIRST page's number —
 *  so a mark anywhere past page one was reported to the tutor under the wrong
 *  page. Harmless while nothing read it; wrong the moment an agent does.
 *  Derived from the DOM instead, which cannot drift out of step with what the
 *  student is looking at. */
function pageUnder(host: HTMLElement, points: Point[]): number {
  const mid = points[Math.floor(points.length / 2)];
  const origin = host.getBoundingClientRect();
  const top = (el: HTMLElement) =>
    el.getBoundingClientRect().top - origin.top + host.scrollTop;
  for (const sheet of host.querySelectorAll<HTMLElement>("[data-page]")) {
    const y = top(sheet);
    if (mid.y >= y && mid.y <= y + sheet.getBoundingClientRect().height) {
      return Number(sheet.dataset.page) || 1;
    }
  }
  return 1;
}

/* Each tool draws as the physical thing it imitates: the marker as a broad
   translucent nib, the circle as a closed loop, the lasso as a dashed one. */

/** The ellipse a circle stroke snaps to. People draw wobbly circles and mean
 *  tidy ones, and the wobble carries no information. Shared by the drawing and
 *  the measuring so that what the student sees is what gets tested — a word
 *  just inside the drawn loop must not fall outside the tested one. */
function ellipseOf(points: Point[]) {
  const b = boundsOf(points);
  return {
    cx: b.x + b.w / 2,
    cy: b.y + b.h / 2,
    rx: Math.max(10, b.w / 2) + 4,
    ry: Math.max(10, b.h / 2) + 4,
  };
}

/** The shape the resolver should test, matching what was drawn. */
function gestureShape(tool: MarkTool, points: Point[]): Point[] {
  if (tool === "marker") {
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const y0 = Math.min(...ys) - NIB, y1 = Math.max(...ys) + NIB;
    return [
      { x: x0, y: y0 }, { x: x1, y: y0 },
      { x: x1, y: y1 }, { x: x0, y: y1 },
    ];
  }

  if (tool === "circle") {
    const { cx, cy, rx, ry } = ellipseOf(points);
    const N = 32;
    return Array.from({ length: N }, (_, i) => {
      const t = (i / N) * Math.PI * 2;
      return { x: cx + rx * Math.cos(t), y: cy + ry * Math.sin(t) };
    });
  }

  return points;
}

function Mark({ stroke, live }: { stroke: Stroke; live?: boolean }) {
  const d = stroke.points.map((p) => `${p.x},${p.y}`).join(" ");
  const opacity = live ? 0.75 : 1;

  if (stroke.tool === "marker") {
    return (
      <polyline
        points={d}
        fill="none"
        stroke="var(--accent)"
        strokeOpacity={0.26 * opacity}
        strokeWidth="17"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    );
  }

  if (stroke.tool === "circle") {
    const e = ellipseOf(stroke.points);
    return (
      <ellipse
        cx={e.cx}
        cy={e.cy}
        rx={e.rx}
        ry={e.ry}
        fill="none"
        stroke="var(--accent)"
        strokeOpacity={0.85 * opacity}
        strokeWidth="2"
      />
    );
  }

  return (
    <polygon
      points={d}
      fill="var(--accent)"
      fillOpacity={0.09 * opacity}
      stroke="var(--accent)"
      strokeOpacity={0.7 * opacity}
      strokeWidth="1.6"
      strokeDasharray="5 4"
    />
  );
}
