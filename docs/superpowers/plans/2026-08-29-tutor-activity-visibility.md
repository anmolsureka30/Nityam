# Tutor Activity Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the tutor delegates to a specialist (BoardAgent, ArtifactAgent, QuizAgent, TextbookAgent), the student sees a friendly, specific cue instead of a generic "Looking that up for you…", and a brief spatial highlight on the board/textbook/quiz-strip that tells them where to look — using the specialist identity the backend already streams but the frontend currently discards.

**Architecture:** One new pure-logic module (`specialists.ts`) maps the tool name ADK already sends (`ask_board`/`ask_artifact`/`ask_quiz`/`ask_textbook`) to a `Specialist` and a fallback phrase. `useLiveSession.ts` captures that identity into one new piece of state, riding the exact lifecycle its existing `thinking`/`bridge` state already has. `SessionScreen.tsx` reads it and drives three additive, class-toggled highlights on components that already exist.

**Tech Stack:** React 19 + TypeScript, Vite 8, CSS Modules, plain `node --test`-free assertion scripts (no test framework — see `frontend/tests/reducer.mjs`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-29-tutor-activity-visibility-design.md`

## Global Constraints

- Zero changes to any file under `backend/` (backend/agent logic is out of scope for this entire sub-project).
- Zero new npm dependencies — verify `frontend/package.json`'s `dependencies`/`devDependencies` are unchanged at the end.
- Glyphs for specialist copy use the app's existing plain-geometric vocabulary, never emoji: board `✎`, artifact `▷`, quiz `?`, textbook `▦`.
- All new CSS animations must have a `prefers-reduced-motion: reduce` fallback, matching the pattern already in `frontend/src/features/session/TextbookPeek.module.css`.
- An unrecognized `ask_*` tool name must always degrade to today's generic behavior (`specialist = null`, no crash, no spatial glow) — never throw, never render `undefined`.
- Every task's automated verification is one of: `node tests/specialists.mjs` (Task 1's new pure-logic tests), `npm test` (full existing suite, unchanged files must still pass), or `npm run build` (`tsc -b && vite build`, the type-check gate) — run from `frontend/`.

---

### Task 1: Specialist resolution module + its tests

**Files:**
- Create: `frontend/src/lib/live/specialists.ts`
- Create: `frontend/tests/specialists.mjs`
- Modify: `frontend/package.json:11` (the `test` script)

**Interfaces:**
- Produces (consumed by Tasks 2 and 3):
  - `export type Specialist = "board" | "artifact" | "quiz" | "textbook"`
  - `export function resolveSpecialist(toolName: string | undefined): Specialist | null`
  - `export const SPECIALIST_COPY: Record<Specialist, { glyph: string; verb: string }>`
  - `export function thinkingLine(bridge: string | undefined, specialist: Specialist | null): string`

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/specialists.mjs`:

```js
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node tests/specialists.mjs`
Expected: FAIL — `ENOENT: no such file or directory, open '.../src/lib/live/specialists.ts'` (the module doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/lib/live/specialists.ts`:

```ts
/* Which specialist the tutor has delegated to, and what to say about it when
 * she hasn't given her own bridge line.
 *
 * Kept as pure functions/data — no React, no hook state — so this is
 * testable exactly the same cheap way notebookReducer.ts already is: see
 * tests/specialists.mjs. useLiveSession.ts is the only caller that matters
 * for real; everything here is plain data transformation.
 */

export type Specialist = "board" | "artifact" | "quiz" | "textbook";

const SPECIALIST_BY_TOOL: Record<string, Specialist> = {
  ask_board: "board",
  ask_artifact: "artifact",
  ask_quiz: "quiz",
  ask_textbook: "textbook",
};

/** `null` for anything unrecognized. A future fifth delegate tool must fall
 *  back to the generic "thinking" copy, never throw and never leave the copy
 *  blank — this is the exact failure mode that broke the app once already,
 *  when the single `ask_tutor` tool these checks used to name was split into
 *  four and no branch matched anything (see useLiveSession.ts's own comment
 *  on this). */
export function resolveSpecialist(toolName: string | undefined): Specialist | null {
  if (!toolName) return null;
  return SPECIALIST_BY_TOOL[toolName] ?? null;
}

/** Fallback phrase, shown only when the tutor hasn't supplied her own bridge
 *  line. Glyphs reuse the app's existing plain-geometric vocabulary rather
 *  than emoji, which would clash with this design system: `board` reuses the
 *  marker-tool glyph (SessionControls.tsx), `textbook` reuses the "View
 *  textbook" glyph (TextbookPeek.tsx). */
export const SPECIALIST_COPY: Record<Specialist, { glyph: string; verb: string }> = {
  board: { glyph: "✎", verb: "Sketching it on the board…" },
  artifact: { glyph: "▷", verb: "Building the simulation…" },
  quiz: { glyph: "?", verb: "Preparing a question…" },
  textbook: { glyph: "▦", verb: "Checking the textbook…" },
};

/** What the "she is thinking" indicator shows. Her own words always win when
 *  present; the specialist-specific phrase is only the fallback for when they
 *  aren't. */
export function thinkingLine(
  bridge: string | undefined,
  specialist: Specialist | null,
): string {
  const line = bridge?.trim();
  if (line) return line;
  if (specialist) {
    const { glyph, verb } = SPECIALIST_COPY[specialist];
    return `${glyph} ${verb}`;
  }
  return "Looking that up for you…";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node tests/specialists.mjs`
Expected: `all passed`, exit code 0.

- [ ] **Step 5: Wire the new test into the project's test script**

Modify `frontend/package.json:11` — append the new test file to the existing chain:

```json
    "test": "node tests/contract.mjs && node tests/kernels.mjs && node tests/grounding.mjs && node tests/reducer.mjs && node tests/ui.mjs && node tests/specialists.mjs"
```

Run: `cd frontend && node tests/contract.mjs && node tests/kernels.mjs && node tests/grounding.mjs && node tests/reducer.mjs && node tests/specialists.mjs`
(Skip `ui.mjs` here — it drives a full headless-Chrome + backend stack and is covered in Task 4's final verification.)
Expected: all five scripts print `all passed`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/live/specialists.ts frontend/tests/specialists.mjs frontend/package.json
git commit -m "feat: add specialist resolution + thinking-line copy module

Pure, tested mapping from the tutor's ask_* delegate tools to a learner-
facing Specialist identity and fallback copy. No wiring into the live
session yet — that's the next task."
```

---

### Task 2: Wire `specialist` state into `useLiveSession`

**Files:**
- Modify: `frontend/src/lib/live/useLiveSession.ts:16-22` (imports), `:24-59` (`LiveTutor` interface), `:85-86` (state), `:205-224` (the `ask_*` matching block), `:243-250` (turnComplete/interrupted clearing), `:455-480` (the returned `useMemo` object)

**Interfaces:**
- Consumes: `Specialist`, `resolveSpecialist` from `frontend/src/lib/live/specialists.ts` (Task 1).
- Produces (consumed by Task 3): `LiveTutor.specialist: Specialist | null`, set the instant an `ask_*` delegation arrives and cleared in the same three places `thinking`/`bridge` already clear (`functionResponse`, `interrupted`, `turnComplete`).

- [ ] **Step 1: Add the import**

Modify `frontend/src/lib/live/useLiveSession.ts:19`, right after the existing `TutorMood` import:

```ts
import type { TutorMood } from "../types";
import type { Specialist } from "./specialists";
import { resolveSpecialist } from "./specialists";
```

- [ ] **Step 2: Add `specialist` to the `LiveTutor` interface**

Modify `frontend/src/lib/live/useLiveSession.ts`, right after the existing `bridge` field (line 42):

```ts
  /** The holding line she gave when she delegated — what she is working on,
   *  in her words. Empty when she is not thinking. */
  bridge: string;
  /** Which specialist she has delegated to, while `thinking` is true. `null`
   *  when she isn't thinking, or when an `ask_*` tool this app doesn't
   *  recognize was reached — see specialists.ts's resolveSpecialist(). */
  specialist: Specialist | null;
```

- [ ] **Step 3: Add the state**

Modify `frontend/src/lib/live/useLiveSession.ts:86`, right after `const [bridge, setBridge] = useState("");`:

```ts
  const [bridge, setBridge] = useState("");
  const [specialist, setSpecialist] = useState<Specialist | null>(null);
```

- [ ] **Step 4: Set it when a delegation arrives**

Modify `frontend/src/lib/live/useLiveSession.ts:205-215` — the existing `ask_*` matching branch:

```ts
      for (const part of event.content?.parts ?? []) {
        if (part.functionCall?.name?.startsWith("ask_")) {
          setThinking(true);
          setSpecialist(resolveSpecialist(part.functionCall.name));
          const line = (part.functionCall.args as { bridge?: string } | undefined)
            ?.bridge?.trim();
          if (line) {
            setBridge(line);
            newTurn();
            say(line);
          }
        }
        /* Belt and braces. These tools are scheduled WHEN_IDLE, and ADK does
           not yield a functionResponse event into this stream for those — so
           in practice it is the turnComplete branch below that clears the
           thinking state, when her own current utterance finishes. */
        if (part.functionResponse?.name?.startsWith("ask_")) {
          setThinking(false);
          setBridge("");
          setSpecialist(null);
        }
      }
```

- [ ] **Step 5: Clear it on `turnComplete`**

Modify `frontend/src/lib/live/useLiveSession.ts:243-250` — the existing clearing block:

```ts
      if (event.interrupted || event.turnComplete) {
        // Belt and braces: a dropped functionResponse must not leave the UI
        // claiming she is still thinking forever.
        if (event.turnComplete) {
          setThinking(false);
          setBridge("");
          setSpecialist(null);
        }
      }
```

- [ ] **Step 6: Return it from the hook**

Modify `frontend/src/lib/live/useLiveSession.ts:455-480` — the returned `useMemo`:

```ts
  return useMemo(
    () => ({
      voice,
      connected,
      mode,
      error,
      listening,
      muted,
      thinking,
      bridge,
      specialist,
      mood,
      caption,
      speakKey,
      heard,
      // Derived, not stored: a muted mic has no level, and zeroing it from an
      // effect would be a second render for a value already known here.
      level: listening ? level : 0,
      board,
      dispatch,
      toggleMute,
      send,
      sendScreen,
    }),
    [voice, connected, mode, error, listening, muted, thinking, bridge, specialist, mood,
     caption, speakKey, heard, level, board, toggleMute, send, sendScreen],
  );
```

- [ ] **Step 7: Verify it type-checks**

Run: `cd frontend && npm run build`
Expected: succeeds with no new TypeScript errors. (This hook has no existing unit test — confirmed during research; a real websocket/ADK event stream backs its only other verification today, which is the mock-mode manual pass in Task 4. `setSpecialist` doesn't need to be added to any `useCallback` dependency array — React guarantees `useState` setters are referentially stable, the same reason `setThinking`/`setBridge` aren't listed either.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/live/useLiveSession.ts
git commit -m "feat: track which specialist the tutor has delegated to

Rides the exact lifecycle thinking/bridge already have. Not yet consumed
by any component."
```

---

### Task 3: Specialist-aware copy in `SessionControls`

**Files:**
- Modify: `frontend/src/features/session/SessionControls.tsx` (imports, props, the thinking-line render)
- Modify: `frontend/src/features/session/SessionScreen.tsx:365-374` (pass the new prop)

**Interfaces:**
- Consumes: `Specialist`, `thinkingLine` from `specialists.ts` (Task 1); `tutor.specialist` from `useLiveSession` (Task 2).
- Produces: `SessionControls` accepts and uses a `specialist` prop; no new exports for later tasks.

- [ ] **Step 1: Import the specialist types/helpers**

Modify `frontend/src/features/session/SessionControls.tsx:1-3`:

```tsx
import { useState } from "react";
import type { MarkTool } from "../../lib/types";
import type { Specialist } from "../../lib/live/specialists";
import { thinkingLine } from "../../lib/live/specialists";
import s from "./SessionControls.module.css";
```

- [ ] **Step 2: Add the `specialist` prop**

Modify `frontend/src/features/session/SessionControls.tsx:13-32` — the component signature:

```tsx
export default function SessionControls({
  tool, onTool, onClear, hasMarks,
  onSend, onEnd, thinking, bridge, specialist,
}: {
  tool: MarkTool | null;
  onTool: (t: MarkTool | null) => void;
  onClear: () => void;
  hasMarks: boolean;
  onSend: (text: string) => void;
  onEnd: () => void;
  /** She has delegated and is waiting. That wait is real — 6-20 seconds — so
   *  it has to be visible or the page reads as broken. */
  thinking: boolean;
  /** What she said she was going off to do, in her own words. Shown instead of
   *  a generic placeholder: "Working that out…" told the student nothing they
   *  could not already see, while the line she actually produced —
   *  "Certainly, I can show you the derivation of the range formula" — was
   *  sitting unused in the tool call. */
  bridge?: string;
  /** Which specialist she has delegated to, when known. Picks the fallback
   *  phrase in thinkingLine() below when `bridge` is absent — `null`/absent
   *  means either she isn't thinking, or an unrecognized delegate tool was
   *  reached (never breaks the UI, just loses the enrichment). */
  specialist?: Specialist | null;
}) {
```

- [ ] **Step 3: Use `thinkingLine()` in the render**

Modify `frontend/src/features/session/SessionControls.tsx:41-50`:

```tsx
      {thinking && (
        <div className={s.heard}>
          <span className={s.thinking}>
            <i /><i /><i />
            <span className={s.thinkingText}>
              {thinkingLine(bridge, specialist ?? null)}
            </span>
          </span>
        </div>
      )}
```

- [ ] **Step 4: Pass the prop from `SessionScreen`**

Modify `frontend/src/features/session/SessionScreen.tsx:365-374` — the existing `<SessionControls>` call:

```tsx
      <SessionControls
        tool={tool}
        onTool={setTool}
        onClear={clearMarks}
        hasMarks={strokes.length > 0}
        onSend={(text) => send({ type: "text", text })}
        thinking={tutor.thinking}
        bridge={tutor.bridge}
        specialist={tutor.specialist}
        onEnd={() => nav("/summary")}
      />
```

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run build`
Expected: succeeds with no new TypeScript errors.

Run: `cd frontend && node tests/specialists.mjs`
Expected: still `all passed` (this task doesn't change `specialists.ts`, just confirms nothing regressed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/session/SessionControls.tsx frontend/src/features/session/SessionScreen.tsx
git commit -m "feat: show a specialist-specific line while the tutor is thinking

'Looking that up for you...' becomes 'Checking the textbook...' /
'Sketching it on the board...' / etc. when she hasn't supplied her own
bridge line. Her own words still always win."
```

---

### Task 4: Spatial cues — board/artifact glow, textbook glow, quiz chip — and final verification

**Files:**
- Modify: `frontend/src/features/session/SessionScreen.tsx:311-332` (the `<main>` stage), `:283-309` (the `.concept` strip), `:348` (the `<TextbookPeek>` call)
- Modify: `frontend/src/features/session/SessionScreen.module.css:118-130` (`.stage` + its media query), end of file (new rules + reduced-motion)
- Modify: `frontend/src/features/session/TextbookPeek.tsx:1, 30-35, 109-116` (imports, props, className)
- Modify: `frontend/src/features/session/TextbookPeek.module.css:8-31` (near `.peek`), `:182-188` (reduced-motion block)

**Interfaces:**
- Consumes: `tutor.specialist` (Task 2), already-passed prop plumbing from Task 3.
- Produces: nothing further consumed by other tasks — this completes the sub-project.

- [ ] **Step 1: Give `.stage` a positioning context and add the glow rules**

Modify `frontend/src/features/session/SessionScreen.module.css:118-124` — the existing `.stage` rule gains `position: relative`:

```css
.stage {
  position: relative;
  flex: 1;
  min-height: 0;
  width: 100%;
  padding: var(--s-5) var(--s-6) 0;
  background: var(--ground-deep);
}
```

Then, right after the existing `@media (max-width: 1240px) { .stage { padding-right: var(--s-4); } }` block (line 130), insert:

```css
/* Tutor activity visibility: a brief glow on the stage while BoardAgent or
   ArtifactAgent is the one she has delegated to. An inset ring on a
   pseudo-element, never a border, so it can never shift the board's layout. */
.stage::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: var(--r-sheet);
  opacity: 0;
  transition: opacity 0.2s var(--ease);
}
.stageBoardActive::after {
  opacity: 1;
  box-shadow: inset 0 0 0 2px var(--accent-tint), inset 0 0 48px -20px var(--accent);
  animation: n-stage-pulse 1.6s ease-in-out infinite;
}
.stageArtifactActive::after {
  opacity: 1;
  box-shadow: inset 0 0 0 2px var(--sim), inset 0 0 48px -20px var(--sim);
  animation: n-stage-pulse 1.6s ease-in-out infinite;
}
@keyframes n-stage-pulse {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 1; }
}
```

- [ ] **Step 2: Add the quiz-preparing chip's styles**

In the same file, right after the `.planNow .planTick` rule (line 155), insert:

```css
/* Tutor activity visibility: a brief chip while QuizAgent is preparing a
   checkpoint question, so the concept strip says so instead of the plan
   steps silently going quiet. */
.quizPrep {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: var(--s-3);
  padding: 3px 10px;
  border-radius: var(--r-pill);
  background: var(--accent-wash);
  border: 1px solid var(--accent-tint);
  color: var(--accent-deep);
  font-family: var(--mono);
  font-size: var(--t-micro);
  letter-spacing: var(--track-micro);
  text-transform: uppercase;
  white-space: nowrap;
  animation: n-quiz-in 0.2s var(--ease) both;
}
@keyframes n-quiz-in {
  from { opacity: 0; transform: translateY(2px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 3: Add the reduced-motion fallback**

At the very end of `frontend/src/features/session/SessionScreen.module.css`, after the existing `@media (max-width: 900px)` block, append:

```css
@media (prefers-reduced-motion: reduce) {
  .stageBoardActive::after,
  .stageArtifactActive::after { animation: none; opacity: 0.85; }
  .quizPrep { animation: none; }
}
```

- [ ] **Step 4: Drive the classes and the chip from `SessionScreen.tsx`**

Modify `frontend/src/features/session/SessionScreen.tsx:311` — the `<main>` stage:

```tsx
      <main
        className={cx(
          s.stage,
          tutor.specialist === "board" && s.stageBoardActive,
          tutor.specialist === "artifact" && s.stageArtifactActive,
        )}
      >
```

Modify `frontend/src/features/session/SessionScreen.tsx:292-309` — the `.concept` strip, adding the quiz chip right after the existing `.plan` div and before the section's closing `</div>`:

```tsx
        <div className={s.plan}>
          {PLAN.map((step, i) => (
            <span
              key={step}
              className={cx(
                s.planStep,
                i < planIndex && s.planDone,
                i === planIndex && s.planNow,
              )}
            >
              <span className={s.planDot}>
                {i < planIndex ? "✓" : i === planIndex ? "●" : i + 1}
              </span>
              {step}
            </span>
          ))}
        </div>

        {tutor.specialist === "quiz" && (
          <span className={s.quizPrep}>? Preparing a question…</span>
        )}
      </div>
```

- [ ] **Step 5: Give `TextbookPeek` an `active` prop and its glow class**

Modify `frontend/src/features/session/TextbookPeek.tsx:1-5` — add a `cx` helper alongside the existing imports:

```tsx
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import catalogue from "../../lib/textbook.json";
import type { Place } from "../../lib/textbookPlace";
import s from "./TextbookPeek.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");
```

Modify `frontend/src/features/session/TextbookPeek.tsx:30-35` — the component signature:

```tsx
export default function TextbookPeek({
  place, onOpen, active,
}: {
  place: Place;
  onOpen: () => void;
  /** True while TextbookAgent is the one currently delegated to — a brief
   *  glow says "watch this" without a second floating indicator. */
  active?: boolean;
}) {
```

Modify `frontend/src/features/session/TextbookPeek.tsx:109-116` — the root `<button>`'s className:

```tsx
  return (
    <button
      type="button"
      className={cx(s.peek, active && s.peekActive)}
      onClick={onOpen}
      title="Open your textbook"
      aria-label={`Open textbook — chapter ${chapter.number}, ${chapter.title}, page ${place.page}`}
    >
```

- [ ] **Step 6: Add the glow CSS**

Modify `frontend/src/features/session/TextbookPeek.module.css`, right after the existing `.peek:focus-visible` rule (line 31), insert:

```css
/* Tutor activity visibility: a brief glow while TextbookAgent is the one
   currently delegated to — reuses the same lift shadow as the existing hover
   state, so it reads as an extension of an interaction that already exists. */
.peekActive {
  animation: n-peek-glow 1.6s ease-in-out infinite;
}
@keyframes n-peek-glow {
  0%, 100% { box-shadow: var(--e-sheet), 0 0 0 2px var(--accent-tint); }
  50%      { box-shadow: var(--e-lift), 0 0 0 2px var(--accent); }
}
```

Modify the existing reduced-motion block at `frontend/src/features/session/TextbookPeek.module.css:185-188`:

```css
@media (prefers-reduced-motion: reduce) {
  .peek:hover { transform: translateX(-50%); }
  .skeleton { animation: none; }
  .peekActive { animation: none; box-shadow: var(--e-lift), 0 0 0 2px var(--accent); }
}
```

- [ ] **Step 7: Pass `active` from `SessionScreen`**

Modify `frontend/src/features/session/SessionScreen.tsx:348` — the existing `<TextbookPeek>` call:

```tsx
      <TextbookPeek
        place={place}
        onOpen={() => setBookOpen(true)}
        active={tutor.specialist === "textbook"}
      />
```

- [ ] **Step 8: Type-check and run the full automated suite**

Run: `cd frontend && npm run build`
Expected: succeeds with no new TypeScript errors.

Run: `cd frontend && npm test`
Expected: all six scripts (`contract`, `kernels`, `grounding`, `reducer`, `ui`, `specialists`) print `all passed`. (`ui.mjs` builds and drives the real app against the backend in mock mode — this is the point at which a regression in the stage/textbook/concept markup would surface, since it exercises the same DOM this task just changed.)

- [ ] **Step 9: Manual verification in mock mode**

Run: `cd backend && ./run.sh` (starts both backend in mock mode and the frontend dev server, per `backend/README.md`)

In the browser, start a session and, for each of the four demo triggers mock mode exercises (or by asking a question that prompts each specialist), confirm:
- The bottom "thinking" line shows a distinct glyph + phrase per specialist (or the tutor's own bridge line, unchanged) — never blank, never "undefined".
- The board/canvas area shows a soft pink glow while `board` is active, a soft blue glow while `artifact` is active, and no glow otherwise.
- `TextbookPeek` (the book preview, top of the right rail) glows while `textbook` is active.
- The concept strip shows a small "? Preparing a question…" chip while `quiz` is active, and it disappears once she moves on.
- All four cues clear within one turn of her finishing — none get stuck on.
- With the OS "reduce motion" setting on, all of the above still appear, just without the pulsing animation.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/session/SessionScreen.tsx frontend/src/features/session/SessionScreen.module.css frontend/src/features/session/TextbookPeek.tsx frontend/src/features/session/TextbookPeek.module.css
git commit -m "feat: spatial cues for board/artifact/textbook/quiz activity

Completes tutor-activity-visibility: a highlight on the stage, the
textbook peek, or the concept strip now shows WHERE the tutor's
delegation will land, driven by the same specialist signal the
thinking-line copy already uses. No backend changes, no new
dependencies."
```
