import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import catalogue from "../../lib/textbook.json";
import type { Place } from "../../lib/textbookPlace";
import s from "./TextbookPeek.module.css";

interface Chapter {
  file: string;
  number: number;
  title: string;
  pages: number;
  sections: { section: string; title: string; page: number }[];
}

const CHAPTERS = catalogue as Chapter[];

/** Small enough to be cheap, large enough that a figure is recognisable. */
const SCALE = 0.7;

/* The book, left open on the desk beside her.
 *
 * There was a "View textbook" button in the header and nothing else — so the
 * book was a thing you had to remember existed, and the rail beside the tutor
 * was empty. A physical textbook does not hide behind a button; it sits open
 * next to you at the page you were on, and you glance at it.
 *
 * So this shows the actual rendered page, at the place the student left it, and
 * opening it is a click on the page itself. It also follows the tutor: when she
 * puts a page on the board, the book turns to it. */
export default function TextbookPeek({
  place, onOpen,
}: {
  place: Place;
  onOpen: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  const chapter = CHAPTERS.find((c) => c.file === place.chapter) ?? CHAPTERS[0];

  /** What the student is looking at, not just where it is.
   *
   *  Several sections routinely start on the same page — 3.1 Introduction and
   *  3.2 Scalars and Vectors both begin on page 1 — so taking the LAST section
   *  at or before the page named 3.2 for a page whose top is 3.1. The preview
   *  shows the top of the page, so among the sections starting on that page the
   *  first one is the right answer; for a page with no section start, the last
   *  heading before it is correct because the page sits inside it. */
  const section = (() => {
    const before = chapter.sections.filter((sec) => sec.page <= place.page);
    if (!before.length) return undefined;
    const start = before[before.length - 1].page;
    return before.find((sec) => sec.page === start);
  })();

  /** The catalogue stores headings as they are printed — all caps. Shouting a
   *  section name in a 12px label is worse than shouting it on a page. */
  const heading = section
    && `${section.section} ${section.title.charAt(0)}${section.title.slice(1).toLowerCase()}`;

  useEffect(() => {
    let dead = false;
    let doc: pdfjs.PDFDocumentProxy | null = null;
    setReady(false);
    setFailed(false);

    (async () => {
      try {
        doc = await pdfjs.getDocument(`/textbook/${place.chapter}.pdf`).promise;
        if (dead) return;
        const p = await doc.getPage(Math.min(place.page, doc.numPages));
        const canvas = ref.current;
        if (dead || !canvas) return;
        const viewport = p.getViewport({ scale: SCALE });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await p.render({ canvas, canvasContext: ctx, viewport }).promise;
        if (!dead) setReady(true);
      } catch {
        if (!dead) setFailed(true);
      }
    })();

    return () => {
      dead = true;
      void doc?.destroy();
    };
  }, [place.chapter, place.page]);

  return (
    <button
      type="button"
      className={s.peek}
      onClick={onOpen}
      title="Open your textbook"
      aria-label={`Open textbook — chapter ${chapter.number}, ${chapter.title}, page ${place.page}`}
    >
      {/* Section first, chapter under it: the section is what the student is
          actually reading, and the chapter line can truncate harmlessly. The
          other way round, the chapter ate the width and the section — the
          useful half — was the one that got cut. */}
      <span className={s.head}>
        <span className={s.spine} aria-hidden="true" />
        <span className={s.headText}>
          <span className={s.where}>{heading ?? `Page ${place.page}`}</span>
          <span className={s.chapter}>Ch {chapter.number} · {chapter.title}</span>
        </span>
      </span>

      <span className={s.paper}>
        {/* The page is masked to a fade at the bottom rather than cut off
            square: a hard crop reads as a broken image, a fade reads as a page
            continuing past the edge of what you can see. */}
        <canvas
          ref={ref}
          className={s.page}
          style={{ opacity: ready ? 1 : 0 }}
          aria-hidden="true"
        />
        {!ready && !failed && <span className={s.skeleton} aria-hidden="true" />}
        {failed && <span className={s.failed}>Could not open the page</span>}
        <span className={s.open}>Open ▦</span>
      </span>

      <span className={s.foot}>
        <span className={s.pageNo}>p.{place.page}</span>
        <span className={s.of}>of {chapter.pages}</span>
      </span>
    </button>
  );
}
