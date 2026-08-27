import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Button, Label } from "../../components/ui";
import catalogue from "../../lib/textbook.json";
import s from "./TextbookDrawer.module.css";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

export interface Chapter {
  file: string;
  number: number;
  title: string;
  kernels: string[];
  pages: number;
  sections: { section: string; title: string; page: number }[];
  figures: { figure: string; page: number }[];
}

export interface Clip {
  /** PNG data URL of the region, already rasterised. */
  image: string;
  /** Any text that fell inside the box — a figure caption, usually. */
  text: string;
  chapter: Chapter;
  page: number;
}

interface Box { x: number; y: number; w: number; h: number; page: number }

const CHAPTERS = catalogue as Chapter[];
/** Rendered at 2× so a clipped diagram is not a blur on a retina screen. */
const SCALE = 2;

/* The real NCERT chapter, rendered from the real PDF.
 *
 * Clipping is the point, not reading: the student drags a box round a figure
 * and it goes onto their page, where the tutor can talk about it and they can
 * mark it like anything else. So the page is a canvas with a selection
 * rectangle over it, rather than a text viewer.
 *
 * The text inside the box is captured too. A diagram with its caption is worth
 * far more to the tutor than a picture it cannot read — it is the difference
 * between "the student pulled in an image" and "the student pulled in Fig 3.14,
 * the one showing the components of the velocity". */
export default function TextbookDrawer({
  onClose, onClip, initialChapter, initialPage, onPlace,
}: {
  onClose: () => void;
  /** All the regions selected, sent together. A figure and the paragraph that
   *  explains it are one thought, and arriving as two separate interruptions is
   *  worse than arriving as one. */
  onClip: (clips: Clip[]) => void;
  /** Which chapter to open on — the concept being taught picks it. */
  initialChapter?: string;
  /** Which page, so closing the drawer and opening it again does not send the
   *  student back to page 1 of chapter 1. A real book stays where you left it. */
  initialPage?: number;
  /** Reported on every turn of the page, so the place survives the drawer. */
  onPlace?: (place: { chapter: string; page: number }) => void;
}) {
  const [chapter, setChapter] = useState<Chapter>(
    CHAPTERS.find((c) => c.file === initialChapter) ?? CHAPTERS[0],
  );
  const [page, setPage] = useState(Math.max(1, initialPage ?? 1));
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /* A list, not a slot. Selecting a second region used to discard the first,
     which made "send me the diagram AND its caption" impossible. */
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [live, setLive] = useState<Box | null>(null);
  /** The rendered page's backing-store size, for placing the boxes. */
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  /* Reported upward rather than lifted into the parent: the drawer owns which
     page is showing while it is open, and the parent only needs to know where
     it ended up. Lifting it would re-render the whole session on every page
     turn. */
  useEffect(() => {
    onPlace?.({ chapter: chapter.file, page });
  }, [chapter.file, page, onPlace]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  const dragFrom = useRef<{ x: number; y: number } | null>(null);
  /* The in-progress box is held in a ref as well as in state. State drives the
     dashed rectangle; the ref is what `up` commits from. Reading it out of a
     `setLive` updater instead meant calling `setBoxes` inside an updater
     function — and React double-invokes updaters under StrictMode, so every
     drag committed the same box twice and one bounding box arrived on the
     canvas as two. Updaters must be pure. */
  const liveRef = useRef<Box | null>(null);
  /** Words on this page with their boxes, for reading text out of a clip. */
  const wordsRef = useRef<{ str: string; x: number; y: number; w: number; h: number }[]>([]);

  // Load the chapter.
  useEffect(() => {
    let dead = false;
    setBusy(true);
    setError(null);
    setBoxes([]);
    setLive(null);
    liveRef.current = null;
    pdfjs
      .getDocument(`/textbook/${chapter.file}.pdf`)
      .promise.then((doc) => {
        if (dead) { void doc.destroy(); return; }
        docRef.current = doc;
        setPage((p) => Math.min(p, doc.numPages));
        setBusy(false);
      })
      .catch((e: Error) => {
        if (dead) return;
        setBusy(false);
        setError(
          `${chapter.title} could not be opened (${e.message}). ` +
          `Run: node scripts/fetch-textbook.mjs`,
        );
      });
    return () => {
      dead = true;
      void docRef.current?.destroy();
      docRef.current = null;
    };
  }, [chapter]);

  // Draw the page, and remember where every word sits.
  useEffect(() => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    if (busy || !doc || !canvas) return;
    let cancelled = false;

    (async () => {
      const pdfPage = await doc.getPage(page);
      if (cancelled) return;
      const viewport = pdfPage.getViewport({ scale: SCALE });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      setSize({ w: canvas.width, h: canvas.height });
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      await pdfPage.render({ canvas, canvasContext: ctx, viewport }).promise;
      if (cancelled) return;

      const content = await pdfPage.getTextContent();
      wordsRef.current = content.items.flatMap((item) => {
        if (!("str" in item) || !item.str.trim()) return [];
        // transform is [a,b,c,d,e,f]; e,f are the PDF-space origin of the run.
        const [, , , , e, f] = item.transform as number[];
        const [x, y] = viewport.convertToViewportPoint(e, f);
        return [{
          str: item.str,
          x,
          y: y - item.height * SCALE,
          w: item.width * SCALE,
          h: item.height * SCALE,
        }];
      });
    })();

    return () => { cancelled = true; };
  }, [busy, page, chapter]);

  const local = (e: React.PointerEvent) => {
    const canvas = canvasRef.current!;
    const r = canvas.getBoundingClientRect();
    // The canvas is displayed smaller than its backing store; work in backing
    // pixels so the crop is sharp rather than upscaled.
    return {
      x: ((e.clientX - r.left) / r.width) * canvas.width,
      y: ((e.clientY - r.top) / r.height) * canvas.height,
    };
  };

  const down = (e: React.PointerEvent) => {
    dragFrom.current = local(e);
    (e.target as Element).setPointerCapture?.(e.pointerId);
    liveRef.current = null;
    setLive(null);
  };
  const move = (e: React.PointerEvent) => {
    const from = dragFrom.current;
    if (!from) return;
    const to = local(e);
    const next: Box = {
      x: Math.min(from.x, to.x), y: Math.min(from.y, to.y),
      w: Math.abs(to.x - from.x), h: Math.abs(to.y - from.y),
      page,
    };
    liveRef.current = next;
    setLive(next);
  };
  const up = () => {
    if (!dragFrom.current) return;      // pointerup and pointercancel both land here
    dragFrom.current = null;
    const box = liveRef.current;
    liveRef.current = null;
    setLive(null);
    // A click is not a selection.
    if (box && box.w > 24 && box.h > 24) setBoxes((prev) => [...prev, box]);
  };

  const crop = useCallback((canvas: HTMLCanvasElement, box: Box): Clip => {
    const out = document.createElement("canvas");
    out.width = Math.round(box.w);
    out.height = Math.round(box.h);
    const ctx = out.getContext("2d")!;
    ctx.drawImage(canvas, box.x, box.y, box.w, box.h, 0, 0, out.width, out.height);

    const inside = wordsRef.current
      .filter((word) =>
        word.x + word.w > box.x && word.x < box.x + box.w &&
        word.y + word.h > box.y && word.y < box.y + box.h)
      .map((word) => word.str)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

    return { image: out.toDataURL("image/png"), text: inside, chapter, page: box.page };
  }, [chapter]);

  const send = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || boxes.length === 0) return;
    /* Only boxes drawn on the page currently rendered can be cropped — the
       canvas holds one page at a time. Anything selected on another page is
       dropped rather than silently cropped from the wrong page. */
    const here = boxes.filter((b) => b.page === page);
    if (here.length === 0) return;
    onClip(here.map((b) => crop(canvas, b)));
    setBoxes([]);
  }, [boxes, page, crop, onClip]);

  const jump = (to: number) => {
    setPage(Math.max(1, Math.min(to, chapter.pages)));
    liveRef.current = null;
    setLive(null);
  };

  /* The rendered size is state, not read off the ref during render. Boxes are
     stored in backing-store pixels and drawn as percentages, so this value has
     to be one React actually re-renders on — a ref read during render is both
     what the linter objects to and how the doubling bug above got in. */
  const asPercent = (b: Box) =>
    size
      ? {
          left: `${(b.x / size.w) * 100}%`,
          top: `${(b.y / size.h) * 100}%`,
          width: `${(b.w / size.w) * 100}%`,
          height: `${(b.h / size.h) * 100}%`,
        }
      : undefined;
  const onThisPage = boxes.filter((b) => b.page === page);
  const elsewhere = boxes.length - onThisPage.length;

  return (
    <div className={s.veil} role="dialog" aria-modal="true" aria-label="Textbook">
      <aside className={s.drawer}>
        <header className={s.head}>
          <div>
            <Label>NCERT · Physics · Class XI</Label>
            <h2 className={s.title}>
              Ch {chapter.number} · {chapter.title}
            </h2>
          </div>
          <button className={s.close} onClick={onClose} aria-label="Close textbook">✕</button>
        </header>

        <div className={s.chapters} role="tablist" aria-label="Chapter">
          {CHAPTERS.map((c) => (
            <button
              key={c.file}
              role="tab"
              aria-selected={c.file === chapter.file}
              className={cx(s.chip, c.file === chapter.file && s.chipOn)}
              onClick={() => { setChapter(c); setPage(1); }}
            >
              {c.number}. {c.title}
            </button>
          ))}
        </div>

        <div className={s.body}>
          <nav className={s.toc} aria-label="Sections">
            {chapter.sections.map((sec) => (
              <button
                key={sec.section}
                className={cx(s.tocItem, sec.page === page && s.tocOn)}
                aria-current={sec.page === page ? "true" : undefined}
                onClick={() => jump(sec.page)}
              >
                <span className={s.tocNum}>{sec.section}</span>
                <span className={s.tocTitle}>{sec.title.toLowerCase()}</span>
              </button>
            ))}
            {chapter.figures.length > 0 && (
              <>
                <span className={s.tocHead}>Figures</span>
                <div className={s.figs}>
                  {chapter.figures.map((f) => (
                    <button key={f.figure} className={s.fig} onClick={() => jump(f.page)}>
                      {f.figure}
                    </button>
                  ))}
                </div>
              </>
            )}
          </nav>

          <div className={s.pageWrap}>
            {error ? (
              <p className={s.error}>{error}</p>
            ) : busy ? (
              <p className={s.loading}>Opening {chapter.title}…</p>
            ) : (
              <div className={s.sheet}>
                <canvas
                  ref={canvasRef}
                  className={s.canvas}
                  onPointerDown={down}
                  onPointerMove={move}
                  onPointerUp={up}
                  onPointerCancel={up}
                />
                {onThisPage.map((b, i) => (
                  <div key={i} className={s.box} style={asPercent(b)} aria-hidden="true">
                    <span className={s.boxNum}>{i + 1}</span>
                  </div>
                ))}
                {live && <div className={s.boxLive} style={asPercent(live)} aria-hidden="true" />}
              </div>
            )}
          </div>
        </div>

        <footer className={s.foot}>
          <div className={s.pager}>
            <button onClick={() => jump(page - 1)} disabled={page <= 1}>←</button>
            <span className={s.pageNum}>
              Page {page} of {chapter.pages}
            </span>
            <button onClick={() => jump(page + 1)} disabled={page >= chapter.pages}>→</button>
          </div>
          <span className={s.hint}>
            {onThisPage.length === 0
              ? "Drag a box round a figure. Drag again to add another."
              : `${onThisPage.length} selected${elsewhere ? ` (${elsewhere} on other pages)` : ""} — drag again to add another.`}
          </span>
          {boxes.length > 0 && (
            <button className={s.clear} onClick={() => setBoxes([])}>
              Clear selection
            </button>
          )}
          <Button
            variant="primary"
            size="sm"
            disabled={onThisPage.length === 0}
            onClick={send}
          >
            Send {onThisPage.length || ""} to my page
          </Button>
        </footer>
      </aside>
    </div>
  );
}
