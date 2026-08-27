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
  onClose, onClip, initialChapter,
}: {
  onClose: () => void;
  onClip: (clip: Clip) => void;
  /** Which chapter to open on — the concept being taught picks it. */
  initialChapter?: string;
}) {
  const [chapter, setChapter] = useState<Chapter>(
    CHAPTERS.find((c) => c.file === initialChapter) ?? CHAPTERS[0],
  );
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [box, setBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  const dragFrom = useRef<{ x: number; y: number } | null>(null);
  /** Words on this page with their boxes, for reading text out of a clip. */
  const wordsRef = useRef<{ str: string; x: number; y: number; w: number; h: number }[]>([]);

  // Load the chapter.
  useEffect(() => {
    let dead = false;
    setBusy(true);
    setError(null);
    setBox(null);
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
    setBox(null);
  };
  const move = (e: React.PointerEvent) => {
    const from = dragFrom.current;
    if (!from) return;
    const to = local(e);
    setBox({
      x: Math.min(from.x, to.x), y: Math.min(from.y, to.y),
      w: Math.abs(to.x - from.x), h: Math.abs(to.y - from.y),
    });
  };
  const up = () => {
    dragFrom.current = null;
    // A click is not a selection.
    setBox((b) => (b && b.w > 24 && b.h > 24 ? b : null));
  };

  const clip = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !box) return;
    const out = document.createElement("canvas");
    out.width = Math.round(box.w);
    out.height = Math.round(box.h);
    const ctx = out.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(canvas, box.x, box.y, box.w, box.h, 0, 0, out.width, out.height);

    const inside = wordsRef.current
      .filter((word) =>
        word.x + word.w > box.x && word.x < box.x + box.w &&
        word.y + word.h > box.y && word.y < box.y + box.h)
      .map((word) => word.str)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

    onClip({ image: out.toDataURL("image/png"), text: inside, chapter, page });
    setBox(null);
  }, [box, chapter, page, onClip]);

  const jump = (to: number) => {
    setPage(Math.max(1, Math.min(to, chapter.pages)));
    setBox(null);
  };

  const view = canvasRef.current;
  const shown = box && view
    ? {
        left: `${(box.x / view.width) * 100}%`,
        top: `${(box.y / view.height) * 100}%`,
        width: `${(box.w / view.width) * 100}%`,
        height: `${(box.h / view.height) * 100}%`,
      }
    : null;

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
                {shown && <div className={s.box} style={shown} aria-hidden="true" />}
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
            {box ? "Ready to send." : "Drag a box round a figure to put it on your page."}
          </span>
          <Button variant="primary" size="sm" disabled={!box} onClick={clip}>
            Send to my page
          </Button>
        </footer>
      </aside>
    </div>
  );
}
