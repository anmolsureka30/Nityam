/* The patch reducer, on its own — no browser, no socket, no model.
 *
 * This is the whole of "the tutor writes on the page", so it is worth being
 * able to test in a second rather than by talking to Gemini. Run against the
 * built bundle's source via a tiny TS strip, so there is no build step here.
 *
 *   node tests/reducer.mjs
 */
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

// Vite 8 ships rolldown rather than esbuild, so strip the types with the
// TypeScript compiler that is already a dependency. Type-only imports vanish,
// which is why the module under test can be loaded with no bundler at all.
const ts = createRequire(import.meta.url)("typescript");
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(resolve(ROOT, "src/lib/notebookReducer.ts"), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const mod = await import("data:text/javascript;base64," + Buffer.from(js).toString("base64"));
const { boardReducer, emptyBoard } = mod;

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};

const patch = (state, p) => boardReducer(state, { type: "patch", patch: p });
const blocks = (s) => s.doc.pages.flatMap((p) => p.blocks);

// ------------------------------------------------------------------ reset
let s = boardReducer(emptyBoard(), {
  type: "reset",
  wire: {
    id: "nb_x", conceptId: "projectile.horizontal_range",
    pages: [{ page: 1, eyebrow: "Revision", blocks: [{ kind: "heading", id: "b_topic", text: "Maximum range" }] }],
  },
});
check("the server's board replaces the local one", blocks(s).length === 1 && s.doc.id === "nb_x");

// ------------------------------------------------------------- append_block
s = patch(s, {
  op: "append_block", page: 1,
  block: {
    kind: "equation", id: "b_eq_1", tex: "R = u² sin(2θ) / g", caption: "range",
    anchors: [{ id: "a_sin", span: "sin(2θ)", concept: "projectile.horizontal_range" }],
  },
});
check("append_block adds it in order", blocks(s).map((b) => b.id).join(",") === "b_topic,b_eq_1",
      blocks(s).map((b) => b.id).join(","));
const eq = blocks(s).find((b) => b.id === "b_eq_1");
check("and its anchors survive, for the tutor to point at",
      eq?.anchors?.[0]?.id === "a_sin", JSON.stringify(eq?.anchors));

// a page the local mirror has never seen must not silently drop the block
s = patch(s, { op: "append_block", page: 2, block: { kind: "heading", id: "b_p2", text: "Next" } });
check("a block for an unseen page creates the page", s.doc.pages.length === 2 && blocks(s).length === 3,
      `${s.doc.pages.length} pages, ${blocks(s).length} blocks`);

// ----------------------------------------------------------------- strike
s = patch(s, { op: "strike", blockId: "b_eq_1" });
const struck = blocks(s).find((b) => b.id === "b_eq_1");
check("strike marks it struck rather than removing it",
      struck?.struck === true && blocks(s).length === 3);

// ------------------------------------------------------------- replace_block
s = patch(s, {
  op: "replace_block", blockId: "b_p2",
  block: { kind: "heading", id: "b_p2", text: "Corrected" },
});
check("replace_block swaps in place",
      blocks(s).find((b) => b.id === "b_p2")?.text === "Corrected" && blocks(s).length === 3);

// ---------------------------------------------------------------- point_at
s = patch(s, { op: "point_at", anchorIds: ["a_sin"], ttlMs: 50 });
check("point_at makes the anchor hot", "a_sin" in s.hot);
const expiredNow = boardReducer(s, { type: "expire_hot", now: Date.now() + 5000 });
check("and it expires, so the page does not stay lit up",
      !("a_sin" in expiredNow.hot));
const notYet = boardReducer(s, { type: "expire_hot", now: Date.now() - 5000 });
check("but not before its ttl", "a_sin" in notYet.hot);
check("expiring nothing returns the same object (no needless rerender)",
      boardReducer(expiredNow, { type: "expire_hot", now: Date.now() }) === expiredNow);

// --------------------------------------------------------------- show_quiz
const q = (id) => ({
  id, index: 1, total: 3, question: `q ${id}`, hint: "", footnote: "",
  options: [{ id: `${id}a`, letter: "A", text: "x", correct: true }],
});
s = patch(s, { op: "show_quiz", checkpoint: q("c_1") });
s = patch(s, { op: "show_quiz", checkpoint: q("c_2") });
s = patch(s, { op: "show_quiz", checkpoint: q("c_3") });
check("a 3-question quiz queues all three, not just the last",
      s.quizQueue.map((c) => c.id).join(",") === "c_1,c_2,c_3",
      s.quizQueue.map((c) => c.id).join(","));
s = boardReducer(s, { type: "quiz_done" });
check("answering one advances the queue",
      s.quizQueue.map((c) => c.id).join(",") === "c_2,c_3");

// -------------------------------------------------------------------- goto
s = patch(s, { op: "goto", blockId: "b_eq_1" });
check("goto asks the view to scroll", s.scrollTo === "b_eq_1");
s = boardReducer(s, { type: "scrolled" });
check("and is consumed once", s.scrollTo === null);

// ------------------------------------------------------------- immutability
const before = s;
const after = patch(s, { op: "append_block", page: 1, block: { kind: "heading", id: "b_z", text: "z" } });
check("patches never mutate the previous state",
      before !== after && blocks(before).length === blocks(after).length - 1);
check("and the revision advances so effects can watch it",
      after.revision > before.revision);

console.log();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
