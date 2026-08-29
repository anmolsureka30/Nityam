/* Build the textbook catalogue the tutor searches.
 *
 *   node scripts/build-textbook-index.mjs
 *
 * Reads the NCERT chapter PDFs in public/textbook/ and writes an index of
 * every numbered section and figure, with the page it is on. Extracted rather
 * than hand-written, because hand-written page numbers rot the moment NCERT
 * reissues a chapter — and they have: the current edition puts Motion in a
 * Plane at chapter 3, not 4, so the app's old hardcoded "Ch 4 · Motion in a
 * plane · p.79" was pointing at Laws of Motion.
 */
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DIR = resolve(ROOT, "public/textbook");
const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");

/** Which chapters we ship, and which kernel each one can be explored with. */
const CHAPTERS = [
  { file: "keph103", number: 3,  title: "Motion in a Plane",
    kernels: ["kinematics2d", "circular2d"] },
  { file: "keph104", number: 4,  title: "Laws of Motion",
    kernels: ["incline2d"] },
  { file: "keph206", number: 13, title: "Oscillations",
    kernels: ["shm1d"] },
  { file: "keph207", number: 14, title: "Waves",
    kernels: ["superposition1d"] },
];

const SECTION = /^(\d{1,2}\.\d{1,2})\s+([A-Z][A-Z \-,'&()]{3,60})$/;
const FIGURE = /Fig\.?\s*(\d{1,2}\.\d{1,2})/g;
/* A CAPTION, as opposed to a mention. A caption is a text run that BEGINS with
   "Fig. 3.14"; a mention is "…are shown in Fig. 3.14 for a…" buried in a
   paragraph. Both used to count, and the index recorded whichever came first in
   reading order — so a figure could be indexed to a page that merely talks
   about it. */
const CAPTION = /^\s*Fig\.?\s*(\d{1,2}\.\d{1,2})\b/;

/** Where a figure sits on its page, as fractions of the page (0..1, origin
 *  top-left, matching CSS).
 *
 *  NCERT sets the caption BELOW the artwork, so the figure is the band between
 *  the caption and whatever text is above it in the same column. That is a
 *  heuristic and it knows it: when the band comes out as a sliver — a caption
 *  with body text immediately above it, which happens for a continued
 *  multi-part figure — it returns null and the reader gets the whole page
 *  instead of a wrong crop. */
function figureBox(items, W, H, num) {
  const escaped = num.replace(".", "\\.");
  const cap = items.find((i) => new RegExp(`^\\s*Fig\\.?\\s*${escaped}\\b`).test(i.str));
  if (!cap) return { box: null, text: null };

  const cx = cap.transform[4];
  const cy = cap.transform[5];
  const ch = cap.height || 10;

  // Which column the caption is in, and how wide that column's text runs.
  const leftCol = cx < W / 2;
  const col = items.filter((i) => (i.transform[4] < W / 2) === leftCol);
  if (!col.length) return { box: null, text: cap.str.trim() };

  /* Column edges come from SUBSTANTIAL runs only. Equation numbers — "(3.30a)"
     and friends — are set hard against the gutter at almost exactly the page
     midpoint, and taking a plain min over every item let one of them drag the
     right column's left edge from 356pt to 302pt. The crop then began in the
     middle of the left column and the student got a slice of body text with
     the figure. */
  const solid = col.filter((i) => i.width > 40);
  const edge = solid.length >= 3 ? solid : col;
  const colL = Math.min(...edge.map((i) => i.transform[4]));
  const colR = Math.max(...edge.map((i) => i.transform[4] + i.width));

  /* PDF space has y increasing upward, so "above the caption" is a larger y.
  
     Only SUBSTANTIAL runs count as the ceiling, for the same reason they define
     the column: a diagram is full of one- and two-character text — axis labels,
     "O", "v", a subscripted symbol — and those sit INSIDE the figure. Counting
     them as "the text above" put the ceiling in the middle of the artwork and
     cropped the top off every graph. */
  const capTop = cy + ch;
  const above = edge.filter((i) => i.transform[5] > capTop + 6);

  /* When nothing substantial sits above — a figure at the top of its column —
     stop below the RUNNING HEADER rather than at the paper's edge. "PHYSICS"
     and its blue rule are set across the top of every page, and they were
     being cropped in as though they were part of the diagram. The header is
     whatever text lives in the top tenth of the sheet. */
  const header = items.filter((i) => i.transform[5] > H * 0.9);
  const ceiling = header.length ? Math.min(...header.map((i) => i.transform[5])) - 8
                                : H - 36;
  const artTop = above.length ? Math.min(...above.map((i) => i.transform[5])) : ceiling;

  /* And the floor is the LAST line of the caption, not the first. NCERT
     captions run to two or three lines — "Fig. 3.14 The components vx and vy of
     velocity v and the angle θ it makes with x-axis…" — and anchoring on the
     matched item alone sliced the explanation off under the picture. */
  const capLines = col.filter(
    (i) => i.transform[5] <= cy + 2 && i.transform[5] > cy - 46,
  );
  const capBottom = capLines.length ? Math.min(...capLines.map((i) => i.transform[5])) : cy;

  // The caption's own printed words, top line to bottom — the box answers
  // "where is it", this answers "what does it show", so a student can find
  // the figure by describing it rather than knowing its number.
  const text = (capLines.length ? capLines : [cap])
    .slice()
    .sort((a, b) => b.transform[5] - a.transform[5])
    .map((i) => i.str)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();

  const top = artTop - 4;
  const bottom = capBottom - 6;
  const h = (top - bottom) / H;
  // Too thin to be a figure, or so tall it is really the whole page: decline
  // the crop box, but the caption text is still good — keep it.
  if (h < 0.06 || h > 0.8) return { box: null, text };

  return {
    box: {
      x: +Math.max(0, (colL - 6) / W).toFixed(4),
      y: +Math.max(0, (H - top) / H).toFixed(4),
      w: +Math.min(1, ((colR - colL) + 12) / W).toFixed(4),
      h: +h.toFixed(4),
    },
    text,
  };
}

const out = [];
for (const ch of CHAPTERS) {
  const path = resolve(DIR, `${ch.file}.pdf`);
  if (!existsSync(path)) {
    console.warn(`  skipped ${ch.file} — not downloaded`);
    continue;
  }
  const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(path)) }).promise;
  const sections = [];
  /** figure -> { page, box, text, hasCaption }. A caption always beats a mention. */
  const figures = new Map();
  /* Per-page keywords, so the tutor can find "friction" — which is discussed at
     length under a heading that never says the word. Headings alone make the
     index look complete and answer almost nothing. */
  const pageText = [];

  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const content = await page.getTextContent();
    const items = content.items.filter((i) => i.str && i.str.trim() && i.transform);
    const { width: W, height: H } = page.getViewport({ scale: 1 });
    const text = content.items.map((i) => i.str).join(" ");
    // Section headings are set on their own line in the source; joined text
    // loses that, so match the numbered form anywhere and tidy it.
    for (const m of text.matchAll(/(\d{1,2}\.\d{1,2})\s+([A-Z][A-Z \-,'&]{4,54})(?=\s{2,}|\s[a-z]|$)/g)) {
      const [, num, raw] = m;
      if (!num.startsWith(`${ch.number}.`)) continue;
      const title = raw.trim().replace(/\s+/g, " ");
      if (title.length < 5) continue;
      if (!sections.some((s) => s.section === num)) sections.push({ section: num, title, page: n });
    }
    /* Captions first, and a caption always wins: it is where the figure IS,
       whereas a mention is only where it is discussed. A figure printed in two
       parts (3.9 runs across two pages) keeps the part with a usable box. */
    for (const item of items) {
      const m = item.str.match(CAPTION);
      if (!m) continue;
      const { box, text: capText } = figureBox(items, W, H, m[1]);
      const held = figures.get(m[1]);
      if (!held || !held.hasCaption || (!held.box && box)) {
        figures.set(m[1], { page: n, box, text: capText, hasCaption: true });
      }
    }
    // Mentions only fill gaps — a figure whose caption never parsed.
    for (const m of text.matchAll(FIGURE)) {
      if (!figures.has(m[1])) figures.set(m[1], { page: n, box: null, text: null, hasCaption: false });
    }

    const words = new Set(
      text.toLowerCase().match(/[a-z][a-z-]{4,}/g) ?? [],
    );
    for (const stop of ["which", "these", "there", "their", "where", "would", "about",
                        "other", "figure", "shown", "given", "since", "value", "along",
                        "equal", "using", "example", "consider", "therefore", "because"]) {
      words.delete(stop);
    }
    pageText.push({ page: n, words: [...words].sort().join(" ") });
  }
  out.push({
    ...ch,
    pages: doc.numPages,
    sections: sections.sort((a, b) => a.section.localeCompare(b.section, undefined, { numeric: true })),
    pageText,
    figures: [...figures.entries()]
      .map(([figure, f]) => ({
        figure, page: f.page,
        ...(f.box ? { box: f.box } : {}),
        ...(f.text ? { caption: f.text } : {}),
      }))
      .sort((a, b) => a.figure.localeCompare(b.figure, undefined, { numeric: true })),
  });
  console.log(`  ${ch.file}  ch ${ch.number} ${ch.title}: ${doc.numPages}p, ` +
              `${sections.length} sections, ${figures.size} figures`);
}

// The browser only needs to navigate; keyword blobs would be dead weight in the
// bundle, so they ship to the backend only.
const forBrowser = out.map(({ pageText, ...rest }) => rest);
writeFileSync(resolve(ROOT, "src/lib/textbook.json"), JSON.stringify(forBrowser, null, 2) + "\n");
writeFileSync(resolve(ROOT, "..", "backend", "app", "textbook_index.json"),
              JSON.stringify(out, null, 2) + "\n");
console.log(`\nwrote src/lib/textbook.json and backend/app/textbook_index.json`);
