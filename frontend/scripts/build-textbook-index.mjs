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

const out = [];
for (const ch of CHAPTERS) {
  const path = resolve(DIR, `${ch.file}.pdf`);
  if (!existsSync(path)) {
    console.warn(`  skipped ${ch.file} — not downloaded`);
    continue;
  }
  const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(path)) }).promise;
  const sections = [];
  const figures = new Map();
  /* Per-page keywords, so the tutor can find "friction" — which is discussed at
     length under a heading that never says the word. Headings alone make the
     index look complete and answer almost nothing. */
  const pageText = [];

  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const text = (await page.getTextContent()).items.map((i) => i.str).join(" ");
    // Section headings are set on their own line in the source; joined text
    // loses that, so match the numbered form anywhere and tidy it.
    for (const m of text.matchAll(/(\d{1,2}\.\d{1,2})\s+([A-Z][A-Z \-,'&]{4,54})(?=\s{2,}|\s[a-z]|$)/g)) {
      const [, num, raw] = m;
      if (!num.startsWith(`${ch.number}.`)) continue;
      const title = raw.trim().replace(/\s+/g, " ");
      if (title.length < 5) continue;
      if (!sections.some((s) => s.section === num)) sections.push({ section: num, title, page: n });
    }
    for (const m of text.matchAll(FIGURE)) {
      if (!figures.has(m[1])) figures.set(m[1], n);
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
      .map(([figure, page]) => ({ figure, page }))
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
