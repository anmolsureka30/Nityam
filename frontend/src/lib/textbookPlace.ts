import { useCallback, useEffect, useState } from "react";
import catalogue from "./textbook.json";

/** Where the student last had the book open. */
export interface Place {
  /** Chapter file stem, e.g. "keph103". */
  chapter: string;
  page: number;
}

const KEY = "nityam.textbook.place";

const CHAPTERS = catalogue as { file: string; pages: number }[];

function valid(place: Place | null): Place | null {
  if (!place) return null;
  const chapter = CHAPTERS.find((c) => c.file === place.chapter);
  if (!chapter) return null;
  const page = Math.max(1, Math.min(Math.round(place.page), chapter.pages));
  return { chapter: place.chapter, page };
}

function read(): Place | null {
  /* Every access is guarded. A private window, cleared site data, or a browser
     set to block storage makes this throw rather than return null, and a
     textbook bookmark is not worth taking the session down for. */
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? valid(JSON.parse(raw) as Place) : null;
  } catch {
    return null;
  }
}

/** Remember the page the student was on, across sessions.
 *
 *  A physical textbook stays open where you left it, and closing the drawer
 *  used to send them back to page 1 of chapter 1 — so a student working through
 *  one section re-navigated to it every single time they wanted a second look.
 *
 *  localStorage rather than session state because the useful span is longer
 *  than one session: they are working through a chapter over a week. It is a
 *  per-viewer convenience, so losing it is harmless and never blocks anything.
 */
export function useTextbookPlace(fallbackChapter?: string) {
  const [place, setPlace] = useState<Place>(
    () =>
      read() ?? {
        chapter:
          CHAPTERS.find((c) => c.file === fallbackChapter)?.file ??
          CHAPTERS[0].file,
        page: 1,
      },
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(place));
    } catch {
      /* Not worth a word to the student: the book still works, it just will
         not be open at the same page tomorrow. */
    }
  }, [place]);

  const goTo = useCallback((next: Place) => {
    const ok = valid(next);
    if (ok) setPlace(ok);
  }, []);

  return [place, goTo] as const;
}
