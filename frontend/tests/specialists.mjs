/* resolveSpecialist(), SPECIALIST_COPY, and thinkingLine(), on their own — no
 * React, no hook state, no socket. Mirrors tests/reducer.mjs's pattern: strip
 * types with the `typescript` package already a dependency, run with no
 * bundler and no browser.
 *
 *   node tests/specialists.mjs
 */
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ts = createRequire(import.meta.url)("typescript");
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(resolve(ROOT, "src/lib/live/specialists.ts"), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const mod = await import("data:text/javascript;base64," + Buffer.from(js).toString("base64"));
const { resolveSpecialist, SPECIALIST_COPY, thinkingLine } = mod;

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};

// ------------------------------------------------------------ resolveSpecialist
check("ask_board resolves to board", resolveSpecialist("ask_board") === "board");
check("ask_artifact resolves to artifact", resolveSpecialist("ask_artifact") === "artifact");
check("ask_quiz resolves to quiz", resolveSpecialist("ask_quiz") === "quiz");
check("ask_textbook resolves to textbook", resolveSpecialist("ask_textbook") === "textbook");
check("an unrecognized ask_ name resolves to null, not a crash",
      resolveSpecialist("ask_tutor") === null);
check("a non-ask_ tool name resolves to null", resolveSpecialist("write_lesson") === null);
check("undefined resolves to null", resolveSpecialist(undefined) === null);

// ------------------------------------------------------------------ copy table
for (const key of ["board", "artifact", "quiz", "textbook"]) {
  const entry = SPECIALIST_COPY[key];
  check(`SPECIALIST_COPY has a glyph+verb for ${key}`,
        typeof entry?.glyph === "string" && entry.glyph.length > 0 &&
        typeof entry?.verb === "string" && entry.verb.length > 0,
        JSON.stringify(entry));
}

// ------------------------------------------------------------------ thinkingLine
check("a real bridge line always wins over the specialist fallback",
      thinkingLine("Certainly, let's look at the range formula", "board")
        === "Certainly, let's look at the range formula");
check("a whitespace-only bridge is treated as absent",
      thinkingLine("   ", "quiz") === `${SPECIALIST_COPY.quiz.glyph} ${SPECIALIST_COPY.quiz.verb}`);
check("no bridge, known specialist: glyph + verb",
      thinkingLine(undefined, "textbook")
        === `${SPECIALIST_COPY.textbook.glyph} ${SPECIALIST_COPY.textbook.verb}`);
check("no bridge, no specialist: the original generic line",
      thinkingLine(undefined, null) === "Looking that up for you…");
check("no bridge, unrecognized specialist: the original generic line",
      thinkingLine(undefined, null) === "Looking that up for you…");

console.log();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
