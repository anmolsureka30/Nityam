/* The grounding resolver, tested without a browser.
 *
 * Node imports .ts directly, so this runs the real module with no build step —
 * the same trick that lets sub_modules_examples/canvas/tests/resolve.js stay a
 * plain script. tests/ui.mjs drives the same code through real layout in
 * Chrome; this file pins the logic that real layout cannot easily provoke: word
 * gaps, sentence bounds, and the coverage maths at its edges.
 *
 *   node tests/grounding.mjs
 */
import {
  SWEPT_FLOOR, buildPacket, coverageOf, describePacket, describeSource,
  groupSweptText, intersects, markerCoverage, polygonCoverage,
} from "../src/lib/grounding.ts";

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};
const eq = (name, got, want) =>
  check(name, got === want, got === want ? "" : `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
const near = (name, got, want, eps = 0.01) =>
  check(name, Math.abs(got - want) < eps, `got ${got}, want ~${want}`);

const words = (s) => s.split(/\s+/);

// ------------------------------------------------------------ swept text

console.log("\ngroupSweptText — what the stroke covered");

{
  const w = words("A projectile leaves the ground at speed v and angle θ.");
  const { text, sentences } = groupSweptText(w, [6, 7, 8, 9, 10]);
  eq("a contiguous run joins with spaces", text, "speed v and angle θ.");
  eq("and widens to the whole sentence", sentences,
     "A projectile leaves the ground at speed v and angle θ.");
}

{
  // The case that made `…` necessary: a lasso can cover both ends of a line
  // and miss its middle. Joining across that gap would quote the tutor a
  // phrase the student never highlighted.
  const { text } = groupSweptText(words("one two three four five"), [0, 1, 3, 4]);
  eq("a gap between covered words becomes an ellipsis", text, "one two … four five");
}

{
  /* The headline case for `sentences`: a stroke that starts and ends
     mid-sentence. The quote is a fragment; the context has to be readable. */
  const w = words(
    "Horizontally nothing slows it down; vertically, gravity brings it back. " +
    "Two independent stories, one shared clock.",
  );
  const { text, sentences } = groupSweptText(w, [8, 9, 10, 11]);
  eq("a mid-sentence sweep quotes exactly what was covered", text, "it back. Two independent");
  eq("and returns both sentences it straddles, whole", sentences,
     "vertically, gravity brings it back. Two independent stories, one shared clock.");
  check("dropping the sentence that was never touched",
        !sentences.includes("Horizontally"), sentences);
}

{
  // An equation has no terminator, so the whole formula is one sentence. That
  // is the right answer: swept "sin(2θ)" is worth little without the R = … .
  const { text, sentences } = groupSweptText(words("R = v² sin(2θ) / g"), [3]);
  eq("a swept equation term quotes just the term", text, "sin(2θ)");
  eq("and carries the whole formula as its context", sentences, "R = v² sin(2θ) / g");
}

{
  const w = words("Why does 45° come out on top? It is the only angle you pick.");
  const { sentences } = groupSweptText(w, [2]);
  eq("a question mark ends a sentence", sentences, "Why does 45° come out on top?");
}

{
  const w = words("He said “stop.” Then he left.");
  const { sentences } = groupSweptText(w, [1]);
  eq("a terminator inside a closing quote still ends the sentence",
     sentences, "He said “stop.”");
}

{
  const { text, sentences } = groupSweptText(words("nothing was covered here"), []);
  eq("covering no words yields no text", text, "");
  eq("and no sentences", sentences, "");
}

{
  // readPage happens to push in order; the contract should not depend on it.
  const { text } = groupSweptText(words("a b c d e"), [4, 2, 2]);
  eq("unsorted and duplicated indices are tolerated", text, "c … e");
}

// --------------------------------------------------------------- the packet

console.log("\nbuildPacket — text plus the block it came from");

{
  const regions = [
    { blockId: "b_intro", kind: "tutor_text", text: "the tail", sentences: "the tail end." },
    { blockId: "b_eq", kind: "equation", text: "R = v² sin(2θ) / g", sentences: "R = v² sin(2θ) / g" },
  ];
  const p = buildPacket("marker", 3, regions);
  eq("the dominant block is the one that gave up the most text", p.blockId, "b_eq");
  eq("text joins every region in document order", p.text, "the tail R = v² sin(2θ) / g");
  eq("regions are carried through untouched", p.regions.length, 2);
  eq("the gesture is reported", p.gesture, "marker");
  eq("so is the page", p.page, 3);
  eq("captured text means confidence 1 — a measured sweep is not a guess", p.confidence, 1);
}

{
  // The simulation hides its text in a shadow root, so it reports a block and
  // no quote. It must still be a region: "you marked the simulation" beats
  // "a blank part of the page".
  const p = buildPacket("circle", 1, [{ blockId: "b_art", kind: "artifact", text: "", sentences: "" }]);
  eq("a textless block is still reported", p.blockId, "b_art");
  eq("with nothing quoted", p.text, "");
  eq("and confidence 0", p.confidence, 0);
}

{
  const p = buildPacket("lasso", 1, []);
  eq("a gesture on nothing has no block", p.blockId, null);
  eq("no text", p.text, "");
  eq("and confidence 0", p.confidence, 0);
}

// ------------------------------------------------------------- description

console.log("\ndescribePacket / describeSource — what the student reads back");

{
  const p = buildPacket("marker", 1, [
    { blockId: "b1", kind: "tutor_text", text: "speed v and angle θ", sentences: "…" },
  ]);
  eq("the summary quotes the swept words", describePacket(p),
     "You marked “speed v and angle θ”.");
  eq("and names the source", describeSource(p), "your notes");
}

{
  const long = "word ".repeat(60).trim();
  const summary = describePacket(buildPacket("marker", 1, [
    { blockId: "b1", kind: "tutor_text", text: long, sentences: long },
  ]));
  const quoted = summary.slice(summary.indexOf("“") + 1, summary.lastIndexOf("”"));
  check("a long sweep is elided rather than filling the screen",
        quoted.endsWith("…") && quoted.length <= 90, `${quoted.length} chars`);
}

{
  const p = buildPacket("circle", 1, [{ blockId: "b_art", kind: "artifact", text: "", sentences: "" }]);
  eq("a textless block is described by what it is", describePacket(p),
     "You marked the simulation.");
}

{
  eq("marking nothing says so plainly", describePacket(buildPacket("lasso", 1, [])),
     "A blank part of the page.");
  eq("and names no source", describeSource(buildPacket("lasso", 1, [])), "");
}

{
  const p = buildPacket("lasso", 1, [
    { blockId: "b1", kind: "tutor_text", text: "a", sentences: "a" },
    { blockId: "b2", kind: "callout", text: "b", sentences: "b" },
    { blockId: "b3", kind: "equation", text: "c", sentences: "c" },
  ]);
  // tutor_text and callout are both "your notes" — naming it twice reads as a
  // bug to the student even though it is literally two blocks.
  eq("sources are named once each, in the order crossed", describeSource(p),
     "your notes · the equation");
}

// ---------------------------------------------------------------- geometry

console.log("\ncoverage — the scoring reused from the canvas module");

{
  const box = { x: 0, y: 0, w: 100, h: 20 };
  near("a marker is scored by the width it sweeps, gated on vertical overlap",
       markerCoverage(box, { x: 0, y: 5, w: 50, h: 18 }), 0.417);
  eq("a swipe that misses vertically scores nothing",
     markerCoverage(box, { x: 0, y: 60, w: 100, h: 18 }), 0);

  /* THE regression this sub-system exists to prevent. A horizontal drag has
     zero raw height, so every vertical-overlap test scores it at zero and the
     student is told "not sure what you marked". AnnotationLayer's NIB inflates
     the band before it ever gets here — this pins why that is load-bearing. */
  eq("a zero-height band scores nothing, which is why NIB exists",
     markerCoverage(box, { x: 0, y: 10, w: 100, h: 0 }), 0);
}

{
  const square = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }, { x: 0, y: 100 }];
  eq("a box fully inside a loop is fully covered",
     polygonCoverage({ x: 10, y: 10, w: 10, h: 10 }, square), 1);
  eq("a box outside it is not covered at all",
     polygonCoverage({ x: 200, y: 200, w: 10, h: 10 }, square), 0);
  eq("a degenerate polygon covers nothing",
     polygonCoverage({ x: 10, y: 10, w: 10, h: 10 }, [{ x: 0, y: 0 }, { x: 1, y: 1 }]), 0);

  const box = { x: 0, y: 0, w: 100, h: 20 };
  const band = { x: 0, y: 5, w: 50, h: 18 };
  eq("coverageOf sends a marker to the band scorer",
     coverageOf("marker", box, square, band), markerCoverage(box, band));
  eq("and a lasso to the polygon scorer",
     coverageOf("lasso", box, square, band), polygonCoverage(box, square));
  eq("a circle is scored as a polygon too",
     coverageOf("circle", box, square, band), polygonCoverage(box, square));
}

{
  const band = { x: 0, y: 0, w: 10, h: 10 };
  check("overlapping boxes intersect", intersects({ x: 5, y: 5, w: 10, h: 10 }, band));
  check("boxes that only share an edge do not",
        !intersects({ x: 10, y: 0, w: 10, h: 10 }, band));
  check("distant boxes do not", !intersects({ x: 50, y: 50, w: 5, h: 5 }, band));
}

near("the swept floor is 0.35 — inclusive on purpose", SWEPT_FLOOR, 0.35, 1e-9);

console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
