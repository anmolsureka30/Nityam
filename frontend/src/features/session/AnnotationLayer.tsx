import { useRef, useState } from "react";
import { boundsOf, resolveGesture } from "../../lib/grounding";
import type { AnchorHit, Box } from "../../lib/grounding";
import type { Anchor, ContextPacket, MarkTool } from "../../lib/types";
import s from "./AnnotationLayer.module.css";

/* Half the drawn nib height. A marker stroke is a horizontal drag, so its raw
 * bounds are a zero-height line and every vertical-overlap test scores zero —
 * the student highlights a word and is told "not sure what you marked". The
 * band has to be as thick as the nib they can see. */
const NIB = 9;

export interface Stroke {
  id: string;
  tool: MarkTool;
  points: { x: number; y: number }[];
}

/* Reads the anchor rects straight out of the DOM at the moment the gesture
 * ends, rather than keeping an index in sync. The layout is the truth; a
 * cached index goes stale the moment the notebook scrolls or an image loads. */
function readAnchors(host: HTMLElement, anchors: Map<string, Anchor>): AnchorHit[] {
  const origin = host.getBoundingClientRect();
  const hits: AnchorHit[] = [];
  host.querySelectorAll<HTMLElement>("[data-anchor]").forEach((el) => {
    const id = el.dataset.anchor!;
    const anchor = anchors.get(id);
    if (!anchor) return;
    const r = el.getBoundingClientRect();
    const box: Box = {
      x: r.left - origin.left + host.scrollLeft,
      y: r.top - origin.top + host.scrollTop,
      w: r.width,
      h: r.height,
    };
    hits.push({ anchor, blockId: el.dataset.block ?? "", box });
  });
  return hits;
}

export default function AnnotationLayer({
  hostRef, tool, anchors, page, strokes, onStroke, onPacket,
}: {
  hostRef: React.RefObject<HTMLDivElement | null>;
  tool: MarkTool | null;
  anchors: Map<string, Anchor>;
  page: number;
  strokes: Stroke[];
  onStroke: (stroke: Stroke) => void;
  onPacket: (packet: ContextPacket) => void;
}) {
  const [live, setLive] = useState<{ x: number; y: number }[]>([]);
  const drawing = useRef(false);

  function toLocal(e: React.PointerEvent): { x: number; y: number } {
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
    onPacket(resolveGesture(tool, gestureShape(tool, points), readAnchors(host, anchors), page));
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

/* Each tool draws as the physical thing it imitates: the marker as a broad
   translucent nib, the circle as a closed loop, the lasso as a dashed one. */
/** The shape the resolver should test, matching what was drawn. */
function gestureShape(tool: MarkTool, points: { x: number; y: number }[]) {
  if (tool !== "marker") return points;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys) - NIB, y1 = Math.max(...ys) + NIB;
  return [
    { x: x0, y: y0 }, { x: x1, y: y0 },
    { x: x1, y: y1 }, { x: x0, y: y1 },
  ];
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
    // Snap to the bounding ellipse: people draw wobbly circles and mean
    // tidy ones, and the wobble carries no information.
    const b = boundsOf(stroke.points);
    return (
      <ellipse
        cx={b.x + b.w / 2}
        cy={b.y + b.h / 2}
        rx={Math.max(10, b.w / 2) + 4}
        ry={Math.max(10, b.h / 2) + 4}
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
