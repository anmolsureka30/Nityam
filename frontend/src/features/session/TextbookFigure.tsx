import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import s from "./Notebook.module.css";

/* A textbook page the TUTOR asked for, rendered where she put it.
 *
 * She sends a chapter and a page, not a picture. The browser already has
 * PDF.js and the file, so it renders the page itself — which keeps a megabyte
 * of base64 off every websocket frame and a PDF rasteriser out of the backend.
 * (A figure the STUDENT clipped arrives the other way, as an image, because
 * they chose the exact region with a mouse.) */
export default function TextbookFigure({
  pdf, page, clip,
}: {
  pdf: string;
  page: number;
  /** Fractions of the page (0..1, origin top-left). When present only that
   *  band is drawn — asking for figure 3.14 and being handed the whole printed
   *  page is the difference between a diagram and a hunt. */
  clip?: { x: number; y: number; w: number; h: number };
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState<string | null>(null);

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
        /* A crop is rendered by sizing the canvas to the band and sliding the
           page under it, NOT by drawing the whole page and scaling it down —
           at 1.6x a tenth of a page would come out at a tenth of the
           resolution. The scale is raised for small crops so a figure fills
           the block as sharply as a full page does. */
        const region = clip ?? { x: 0, y: 0, w: 1, h: 1 };
        const base = p.getViewport({ scale: 1 });
        const scale = Math.min(4, 1.6 / Math.max(0.28, region.w));
        const viewport = p.getViewport({ scale });

        canvas.width = Math.round(base.width * region.w * scale);
        canvas.height = Math.round(base.height * region.h * scale);
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await p.render({
          canvas,
          canvasContext: ctx,
          viewport,
          transform: [1, 0, 0, 1,
                      -base.width * region.x * scale,
                      -base.height * region.y * scale],
        }).promise;
      } catch (e) {
        if (!dead) setFailed((e as Error).message);
      }
    })();

    return () => {
      dead = true;
      void doc?.destroy();
    };
  }, [pdf, page, clip?.x, clip?.y, clip?.w, clip?.h]);

  if (failed) {
    return <p className={s.pulledBody}>That textbook page could not be opened ({failed}).</p>;
  }
  return <canvas ref={ref} className={s.figureImg} aria-label={`Textbook page ${page}`} />;
}
