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
export default function TextbookFigure({ pdf, page }: { pdf: string; page: number }) {
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
        const viewport = p.getViewport({ scale: 1.6 });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await p.render({ canvas, canvasContext: ctx, viewport }).promise;
      } catch (e) {
        if (!dead) setFailed((e as Error).message);
      }
    })();

    return () => {
      dead = true;
      void doc?.destroy();
    };
  }, [pdf, page]);

  if (failed) {
    return <p className={s.pulledBody}>That textbook page could not be opened ({failed}).</p>;
  }
  return <canvas ref={ref} className={s.figureImg} aria-label={`Textbook page ${page}`} />;
}
