/* Breaking her speech into bubble-sized pieces — no browser, no socket.
 *
 * The inputs here are real settled transcriptions taken out of
 * backend/logs, because the failure this fixes was a real one: a
 * three-sentence reply arrived as a single transcription and filled the bubble
 * with a paragraph.
 *
 *   node tests/chunks.mjs
 */
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ts = createRequire(import.meta.url)("typescript");
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(resolve(ROOT, "src/lib/live/chunks.ts"), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { toChunks, spokenMs } = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};
const words = (t) => t.trim().split(/\s+/).filter(Boolean).length;

// ── the case this exists for ────────────────────────────────────────────────
/* Verbatim from backend/logs/2026-08-27_13-58 — ONE settled transcription. */
const real =
  "Maine board par height aur range dono ke formulas note kar diye hain. " +
  "Maximum height vertical velocity decide karti hai, lekin range ke liye angle " +
  "sabse crucial factor hai. Agar fixed speed se ball hit karein, toh maximum " +
  "range pane ke liye angle kya hona chahiye?";

const chunks = toChunks(real);
check("a three-sentence reply becomes several chunks", chunks.length >= 3,
      `${chunks.length} chunks from ${words(real)} words`);
check("and none of them is a paragraph",
      chunks.every((c) => words(c) <= 12),
      `longest is ${Math.max(...chunks.map(words))} words`);
check("nothing she said is lost",
      chunks.join(" ").replace(/\s+/g, " ") === real.replace(/\s+/g, " "),
      chunks.join(" ").slice(0, 60));

// ── a long sentence still has to break ──────────────────────────────────────
/* 14 words in one sentence: splitting on sentences alone leaves this too long,
   which is why a clause split exists. */
const longOne = "Maximum height vertical velocity decide karti hai, lekin range ke liye angle sabse crucial factor hai.";
const split = toChunks(longOne);
check("a single long sentence is broken at a clause", split.length === 2,
      split.map((c) => `"${c}"`).join(" | "));
check("and it breaks at the comma, where a speaker breathes",
      split[0].endsWith(",") || split[1].startsWith("lekin"),
      split.join(" | "));

// ── short things are left alone ─────────────────────────────────────────────
check("a holding line stays one chunk",
      toChunks("Achha, ek second.").length === 1);
check("a single question stays one chunk",
      toChunks("What angle makes the sine function the biggest?").length === 1,
      JSON.stringify(toChunks("What angle makes the sine function the biggest?")));

// ── Hindi ───────────────────────────────────────────────────────────────────
/* She switches to Devanagari mid-session, and the danda ends a sentence there.
   Without it the whole Hindi reply is one chunk. */
const hindi = "यह बहुत अच्छा सवाल है। अब ध्यान दीजिए कि कोण क्या करता है।";
check("the Devanagari danda ends a sentence", toChunks(hindi).length === 2,
      JSON.stringify(toChunks(hindi)));

// ── runts ───────────────────────────────────────────────────────────────────
/* A two-word tail flashed up on its own reads as a stutter, so it is glued to
   its predecessor. */
const runt = toChunks("Look at the sine term on the board. Yes.");
check("a runt sentence is glued to the one before it", runt.length === 1,
      JSON.stringify(runt));

// ── no punctuation at all ───────────────────────────────────────────────────
/* Transcription sometimes returns a whole turn with no full stops. It still
   must not become one 24-word bubble. */
const bare = "so gravity controls airtime and forty five degrees gives the perfect balance but the angle never changes regardless of the planet you are standing on";
const bareChunks = toChunks(bare);
check("an unpunctuated turn is still broken up", bareChunks.length >= 2,
      `${bareChunks.length} chunks, longest ${Math.max(...bareChunks.map(words))} words`);
check("and still loses nothing",
      bareChunks.join(" ") === bare, bareChunks.join(" ").slice(0, 50));

// ── degenerate input ────────────────────────────────────────────────────────
check("empty text produces no chunks", toChunks("").length === 0);
check("whitespace produces no chunks", toChunks("   \n  ").length === 0);

// ── pacing ──────────────────────────────────────────────────────────────────
check("a longer chunk is given longer to be said",
      spokenMs("one two three four five six seven eight") > spokenMs("one two three"));
check("and even a one-word chunk gets long enough to read",
      spokenMs("Exactly.") >= 900, `${spokenMs("Exactly.")}ms`);

console.log();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
