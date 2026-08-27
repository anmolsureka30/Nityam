/* Reading what a gesture covered off the page.
 *
 * The DOM half of grounding. It measures at the moment the gesture ends rather
 * than keeping an index in sync, because the layout is the truth: a cached
 * index goes stale the moment the notebook scrolls, an image loads, or a pulled
 * note is appended.
 *
 * The unit of measurement is a WORD. Anything coarser cannot answer "what did I
 * actually highlight" — a block-level answer reports a paragraph when the
 * student swiped four words of it — and anything finer costs measurements
 * without changing the text that comes out.
 */

import { boundsOf, coverageOf, groupSweptText, intersects, SWEPT_FLOOR } from "../../lib/grounding";
import type { Box, Point } from "../../lib/grounding";
import type { MarkTool, NotebookBlock, SweptRegion } from "../../lib/types";

/** One word, and where in the DOM it lives so it can be measured. */
interface Word {
  node: Text;
  start: number;
  end: number;
  text: string;
}

/** Every non-whitespace run inside `block`, in document order.
 *
 *  Text inside an anchor `<mark>` is included, because it is part of the
 *  paragraph the student is reading — an anchored term under the stroke comes
 *  back as text like any other word. */
function wordsIn(block: HTMLElement): Word[] {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  const words: Word[] = [];
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    for (const m of node.data.matchAll(/\S+/g)) {
      words.push({ node, start: m.index, end: m.index + m[0].length, text: m[0] });
    }
  }
  return words;
}

/** Which page the gesture landed on is decided by the gesture's own position,
 *  not by anything here — see `pageUnder` in AnnotationLayer.tsx. */
export function readSweptRegions(host: HTMLElement, tool: MarkTool, poly: Point[]): SweptRegion[] {
  const band = boundsOf(poly);
  const origin = host.getBoundingClientRect();
  const dx = host.scrollLeft - origin.left;
  const dy = host.scrollTop - origin.top;
  const local = (r: DOMRect): Box => ({ x: r.left + dx, y: r.top + dy, w: r.width, h: r.height });

  const regions: SweptRegion[] = [];
  const range = document.createRange();

  // Block wrappers only. Anchor <mark>s carry data-anchor and data-block but
  // never data-kind, so there is no nesting collision to filter out.
  host.querySelectorAll<HTMLElement>("[data-kind]").forEach((block) => {
    if (!intersects(local(block.getBoundingClientRect()), band)) return;

    const blockId = block.dataset.block ?? "";
    // Stamped from the typed block in Notebook.tsx, so it is always a real kind.
    const kind = block.dataset.kind as NotebookBlock["kind"];

    const words = wordsIn(block);
    if (words.length === 0) {
      /* No words to quote, so the block rect is the only thing there is to
         measure. Reported anyway: a gesture on the simulation must not come
         back as a blank part of the page. ArtifactBlock puts its content in a
         shadow root, which is deliberately opaque to this walk — "you marked
         the simulation" beats quoting its internal axis labels. */
      regions.push({ blockId, kind, text: "", sentences: "" });
      return;
    }

    const kept: number[] = [];
    words.forEach((word, i) => {
      range.setStart(word.node, word.start);
      range.setEnd(word.node, word.end);
      // A word can report more than one rect when it straddles a line break;
      // the most-covered one is what the student was pointing at.
      const rects = range.getClientRects();
      let best = 0;
      for (let r = 0; r < rects.length; r++) {
        best = Math.max(best, coverageOf(tool, local(rects[r]), poly, band));
      }
      if (best >= SWEPT_FLOOR) kept.push(i);
    });

    if (kept.length === 0) return;
    const { text, sentences } = groupSweptText(words.map((w) => w.text), kept);
    /* The simulation's words are captions and axis labels, not prose, so
       widening to "the sentence they sit in" would return the whole widget's
       chrome as one run-on line. An equation is the opposite case: it has no
       terminator either, and returning the whole formula around a swept term is
       exactly the context the tutor wants. */
    regions.push({ blockId, kind, text, sentences: kind === "artifact" ? text : sentences });
  });

  return regions;
}
