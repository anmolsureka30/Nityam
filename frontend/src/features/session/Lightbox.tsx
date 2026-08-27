import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import s from "./Lightbox.module.css";

/* Click a figure, get it full size and zoomable — the Discord gesture set.
 *
 * Two kinds of thing arrive here for the same reason and by different routes:
 * a region the student clipped (already an image) and a page the tutor asked
 * for by number (rendered locally by PDF.js). A textbook page at the size it
 * sits in the notebook is unreadable, which made the tutor's best move — "look
 * at figure 3.9" — the one thing the student could not actually do.
 *
 * The PDF is re-rendered here at a higher scale rather than the notebook's
 * canvas being scaled up. Blowing up a 1.6-scale raster gives you big blurry
 * text, which is worse than the small sharp text you started with. */

export type LightboxSource =
  | { kind: "image"; src: string }
  | { kind: "pdf"; pdf: string; page: number };

const MIN = 1;
const MAX = 8;

/** Enough resolution that 8x still resolves NCERT body text, capped so a
 *  retina screen does not ask for a 200-megapixel canvas. */
const RENDER_SCALE = 3.2;

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export default function Lightbox({
  source,
  caption,
  onClose,
}: {
  source: LightboxSource;
  caption?: string;
  onClose: () => void;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  /* One piece of state, not three, so every update is a single PURE function of
     the previous view.
     
     The first version kept scale, tx and ty separately and called setTx/setTy
     from inside the setScale updater. React double-invokes updaters in
     development, so each wheel notch applied its translation twice: at 374%
     the offset came out as 3721px instead of 784 and the figure was flung
     clean off the screen — while a test asserting only "the transform changed"
     passed happily. Same trap as the textbook-clip doubling. A pure updater is
     immune: run it twice with the same input and you get the same answer. */
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const { scale, tx, ty } = view;
  const [dragging, setDragging] = useState(false);

  const reset = useCallback(() => setView({ scale: 1, tx: 0, ty: 0 }), []);

  /* Keep the figure covering the stage, never dragged out into the dark.
   *
   * The standard no-empty-gutter clamp: the scaled content may be offset by at
   * most half its overhang. When it is smaller than the stage there is no
   * overhang and it stays centred, which is also what "fit" should mean. */
  const bound = useCallback(
    (v: { scale: number; tx: number; ty: number }) => {
      const box = stage.current?.getBoundingClientRect();
      const art = holder.current;
      if (!box || !art) return v;
      const limitX = Math.max(0, (art.offsetWidth * v.scale - box.width) / 2);
      const limitY = Math.max(0, (art.offsetHeight * v.scale - box.height) / 2);
      return {
        scale: v.scale,
        tx: clamp(v.tx, -limitX, limitX),
        ty: clamp(v.ty, -limitY, limitY),
      };
    },
    [],
  );

  /* Zoom about a point, not about the middle.
   *
   * Zooming to the centre when the cursor is over the corner of a diagram
   * walks the thing you were looking at off screen and you chase it with the
   * mouse. Keeping the point under the cursor fixed is what makes wheel-zoom
   * feel like a magnifier instead of a slider. */
  const zoomAt = useCallback(
    (factor: number, clientX?: number, clientY?: number) => {
      const box = stage.current?.getBoundingClientRect();
      setView((v) => {
        const next = clamp(v.scale * factor, MIN, MAX);
        if (next === v.scale) return v;
        if (next === MIN) return { scale: MIN, tx: 0, ty: 0 };
        if (!box) return { ...v, scale: next };
        const px = (clientX ?? box.left + box.width / 2) - box.left - box.width / 2;
        const py = (clientY ?? box.top + box.height / 2) - box.top - box.height / 2;
        const ratio = next / v.scale;
        return bound({
          scale: next,
          tx: px - (px - v.tx) * ratio,
          ty: py - (py - v.ty) * ratio,
        });
      });
    },
    [bound],
  );

  /* Escape, and the keyboard equivalents of the zoom controls, so this is
     usable without a trackpad. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "+" || e.key === "=") {
        zoomAt(1.35);
      } else if (e.key === "-" || e.key === "_") {
        zoomAt(1 / 1.35);
      } else if (e.key === "0") {
        reset();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, zoomAt, reset]);

  /* The page behind must not scroll while this is open, and it must go back to
     exactly where it was — the notebook is long and losing your place in it is
     the whole cost of opening a figure. */
  useEffect(() => {
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
    };
  }, []);

  /* Non-passive, because a wheel over the figure must zoom rather than scroll
     the page, and preventDefault is not allowed on a passive listener. React's
     onWheel is registered passively, so this has to be attached by hand. */
  useEffect(() => {
    const node = stage.current;
    if (!node) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomAt(Math.exp(-e.deltaY * 0.0022), e.clientX, e.clientY);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  /* Drag to pan, and pinch to zoom, off one set of pointer events.
     Two pointers down means a pinch; one means a pan. */
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<number | null>(null);

  const spread = () => {
    const [a, b] = [...pointers.current.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) pinch.current = spread();
    else if (scale > MIN) setDragging(true);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const previous = pointers.current.get(e.pointerId);
    if (!previous) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pointers.current.size === 2 && pinch.current) {
      const now = spread();
      const [a, b] = [...pointers.current.values()];
      zoomAt(now / pinch.current, (a.x + b.x) / 2, (a.y + b.y) / 2);
      pinch.current = now;
      return;
    }
    if (pointers.current.size === 1 && scale > MIN) {
      const dx = e.clientX - previous.x;
      const dy = e.clientY - previous.y;
      setView((v) => bound({ ...v, tx: v.tx + dx, ty: v.ty + dy }));
    }
  };

  const endPointer = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (pointers.current.size === 0) setDragging(false);
  };

  const zoomed = scale > MIN + 0.001;

  return (
    <div
      className={s.veil}
      role="dialog"
      aria-modal="true"
      aria-label={caption || "Figure"}
      /* Only a click that both starts and ends on the backdrop closes it.
         Releasing a pan gesture over the veil used to dismiss the thing you
         were in the middle of examining. */
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) e.currentTarget.dataset.from = "veil";
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && e.currentTarget.dataset.from === "veil") {
          onClose();
        }
        delete e.currentTarget.dataset.from;
      }}
    >
      <div className={s.bar}>
        <span className={s.caption}>{caption}</span>
        <div className={s.tools}>
          <button
            type="button"
            className={s.tool}
            onClick={() => zoomAt(1 / 1.4)}
            disabled={!zoomed}
            aria-label="Zoom out"
            title="Zoom out  ( − )"
          >
            −
          </button>
          <button
            type="button"
            className={s.zoomLevel}
            onClick={reset}
            disabled={!zoomed}
            aria-label="Reset zoom"
            title="Fit to screen  ( 0 )"
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            type="button"
            className={s.tool}
            onClick={() => zoomAt(1.4)}
            disabled={scale >= MAX}
            aria-label="Zoom in"
            title="Zoom in  ( + )"
          >
            +
          </button>
          <button
            ref={closeRef}
            type="button"
            className={`${s.tool} ${s.close}`}
            onClick={onClose}
            aria-label="Close"
            title="Close  ( Esc )"
          >
            ✕
          </button>
        </div>
      </div>

      <div
        ref={stage}
        className={`${s.stage} ${zoomed ? s.stageZoomed : ""} ${dragging ? s.stageDragging : ""}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onDoubleClick={(e) => (zoomed ? reset() : zoomAt(2.6, e.clientX, e.clientY))}
      >
        <div
          ref={holder}
          className={s.holder}
          style={{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }}
        >
          {source.kind === "image" ? (
            <img className={s.art} src={source.src} alt={caption || "Figure"} draggable={false} />
          ) : (
            <PdfPage pdf={source.pdf} page={source.page} />
          )}
        </div>
      </div>

      <p className={s.hint}>
        {zoomed ? "Drag to move · double-click to fit" : "Scroll or double-click to zoom"}
        <span className={s.hintKeys}> · Esc to close</span>
      </p>
    </div>
  );
}

/** The same page as the notebook's, re-rendered large enough to survive 8x. */
function PdfPage({ pdf, page }: { pdf: string; page: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let dead = false;
    let doc: pdfjs.PDFDocumentProxy | null = null;

    (async () => {
      try {
        doc = await pdfjs.getDocument(`/textbook/${pdf}.pdf`).promise;
        if (dead) return;
        const p = await doc.getPage(page);
        const canvas = ref.current;
        if (dead || !canvas) return;
        const viewport = p.getViewport({ scale: RENDER_SCALE });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await p.render({ canvas, canvasContext: ctx, viewport }).promise;
        if (!dead) setReady(true);
      } catch (e) {
        if (!dead) setFailed((e as Error).message);
      }
    })();

    return () => {
      dead = true;
      void doc?.destroy();
    };
  }, [pdf, page]);

  if (failed) return <p className={s.failed}>That page could not be opened ({failed}).</p>;
  return (
    <>
      {!ready && <p className={s.loading}>Opening the page…</p>}
      <canvas
        ref={ref}
        className={s.art}
        style={{ visibility: ready ? "visible" : "hidden" }}
        aria-label={`Textbook page ${page}`}
      />
    </>
  );
}
