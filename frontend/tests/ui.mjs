/* Drives the whole product in headless Chrome over the DevTools protocol.
 *
 * One server: the backend in mock mode, serving the built frontend and the real
 * WebSocket from the same port. No Vite proxy, no fake socket — the page here
 * talks to the same read_client()/outbox path the live tutor uses, so what this
 * proves is the actual wiring rather than a stand-in for it. Mock mode means no
 * credentials and no spend.
 *
 * Guards, in order of what has actually broken before:
 *   - the tutor writing on the board at all (the point of the whole build)
 *   - grounding: a horizontal marker drag has zero height, so scoring anchors
 *     by vertical overlap once rejected every highlight and told the student
 *     "not sure what you marked" — the worst failure here, because they
 *     pointed at something and were ignored
 *   - the avatar being drawn, transparent, and animating
 *   - content being scrollable clear of the avatar
 *
 *   npm run build && node tests/ui.mjs
 */
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = resolve(ROOT, "..", "backend");
const OUT = process.env.NITYAM_SHOTS ?? tmpdir();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () =>
  new Promise((r) => {
    const s = createServer();
    s.unref();
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => r(port));
    });
  });

const APP = await freePort(), CDP = await freePort();

const srv = spawn(
  resolve(BACKEND, ".venv/bin/uvicorn"),
  ["app.main:app", "--port", String(APP), "--log-level", "warning"],
  { cwd: BACKEND, env: { ...process.env, NITYAM_AUTH: "mock" }, stdio: "ignore" },
);
const profile = mkdtempSync(resolve(tmpdir(), "nity-v-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME,
  ["--headless=new", `--remote-debugging-port=${CDP}`, `--user-data-dir=${profile}`,
   "--no-first-run", "--disable-gpu", "--hide-scrollbars", "--window-size=1440,1000",
   "about:blank"], { stdio: "ignore" });
const reap = () => { chrome.kill("SIGKILL"); srv.kill("SIGKILL"); };
process.on("exit", reap);
// Without these, killing a run part-way leaves the server and Chrome listening.
// A dozen orphaned previews had piled up from the version of this file that
// only handled "exit".
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => { reap(); process.exit(130); });
}
process.on("uncaughtException", (e) => { reap(); throw e; });

for (let i = 0; i < 250; i++) {
  try { if ((await fetch(`http://127.0.0.1:${APP}/health`)).ok) break; } catch {}
  await sleep(120);
}
let url;
for (let i = 0; i < 90; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();
    const page = list.find((t) => t.type === "page");
    if (page?.webSocketDebuggerUrl) { url = page.webSocketDebuggerUrl; break; }
  } catch {}
  await sleep(150);
}

let id = 1;
const pend = new Map();
const ws = new WebSocket(url);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
ws.onmessage = ({ data }) => {
  const p = JSON.parse(data);
  const w = pend.get(p.id);
  if (w) { pend.delete(p.id); p.error ? w.reject(new Error(p.error.message)) : w.resolve(p.result); }
};
const send = (m, p = {}) =>
  new Promise((res, rej) => { const i = id++; pend.set(i, { resolve: res, reject: rej }); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
const ev = async (e) => {
  const r = await send("Runtime.evaluate", { expression: `(async()=>{${e}})()`, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description);
  return r.result.value;
};
await send("Page.enable"); await send("Runtime.enable");
const errs = [];
ws.addEventListener("message", ({ data }) => {
  const p = JSON.parse(data);
  if (p.method === "Runtime.exceptionThrown") errs.push(p.params.exceptionDetails.text);
});

let failed = 0;

const ask = async (text) => {
  await ev(`document.querySelector('input[aria-label="Ask Nityam"]').focus(); return 1;`);
  await send("Input.insertText", { text });
  // `text` matters: without it Chrome delivers the key but never the character,
  // and a form's implicit submission does not fire.
  await send("Input.dispatchKeyEvent", {
    type: "keyDown", key: "Enter", code: "Enter", text: "\r",
    windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
  });
  await send("Input.dispatchKeyEvent", {
    type: "keyUp", key: "Enter", code: "Enter",
    windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
  });
};

const check = (n, ok, extra = "") => { if (!ok) failed++; console.log(`${ok ? "  ok  " : "  FAIL"} ${n}${extra ? " — " + extra : ""}`); };

await send("Page.navigate", { url: `http://127.0.0.1:${APP}/session` });
await sleep(2500);

const blocks = () => ev(`return [...document.querySelectorAll('[data-kind]')].map(e=>({kind:e.dataset.kind,id:e.dataset.block,text:e.textContent.slice(0,60)}));`);

// ─────────────────────────────────────────────── the board fills as she talks
const opening = await blocks();
check("the board opens on the topic heading, nothing pre-baked",
      opening[0]?.kind === "heading" && opening.length <= 2, JSON.stringify(opening.map(b=>b.kind)));
check("her opening line was written, not bundled",
      opening.some((b) => b.kind === "tutor_text"), JSON.stringify(opening.map(b=>b.kind)));

await ask('why is 45 the best angle?');
await sleep(1800);

const written = await blocks();
check("asking a question makes her write on the board", written.length > opening.length,
      `${opening.length} -> ${written.length} blocks`);
const eqEl = written.find((b) => b.kind === "equation");
check("including the formula", !!eqEl, JSON.stringify(written.map((b) => b.kind)));
check("with no leftover [[ ]] anchor markup",
      !written.some((b) => b.text.includes("[[")),
      JSON.stringify(written.filter((b) => b.text.includes("[["))));
check("she speaks as well as writes",
      await ev("const b=document.querySelector('[role=status]'); return !!b && b.innerText.length>10;"));

// ───────────────────────────────────────────────────────────── the grounding
await ev(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Marker')).click(); return 1;`);
await sleep(250);
const box = await ev(`
  const el = [...document.querySelectorAll('[data-kind="equation"]')][0];
  const r = el.getBoundingClientRect();
  return {x:Math.round(r.left), y:Math.round(r.top+r.height/2), w:Math.round(r.width)};
`);
const drag = (type, x, y) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: 1, pointerType: "mouse", clickCount: 1 });
await drag("mousePressed", box.x - 6, box.y);
for (let i = 0; i <= 10; i++) await drag("mouseMoved", box.x - 6 + ((box.w + 12) * i) / 10, box.y);
await drag("mouseReleased", box.x + box.w + 6, box.y);
await sleep(600);

// The curly quote matters: "You marked on the page" is the card's LABEL, and
// matching it made this check pass without any text having been swept at all.
const summary = await ev(`
  const el = [...document.querySelectorAll('*')].find(e=>e.children.length===0 && /^You marked \u201c/.test(e.textContent.trim()));
  return el ? el.textContent.trim() : null;
`);
check("marking the page quotes the words actually swept",
      !!summary && /sin|2\u03b8|R =/.test(summary), summary ?? "no quote at all");
check("and names where it came from",
      await ev("return document.body.innerText.includes('the equation');"));

await ev(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Ask about this'))?.click(); return 1;`);
await sleep(1800);
const after = await blocks();
check("asking about the mark reaches the tutor and she responds",
      after.length >= written.length,
      `${written.length} -> ${after.length} blocks`);

/* The bug this feature was built to fix. The sweep above lands on the equation,
   which holds `sin(2\u03b8)` — an authored anchor — so it would have passed under
   the old anchor-scoring resolver too. Unanchored prose is what actually broke:
   the resolver had nothing to score, and the student was told they had marked a
   blank part of the page. Sweep a paragraph with no anchors in it at all. */
await ev(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Clear')?.click(); return 1;`);
await ev(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Marker')).click(); return 1;`);
await sleep(250);

const prose = await ev(`
  const el = [...document.querySelectorAll('[data-kind="tutor_text"]')]
    .find(e => !e.querySelector('[data-anchor]') && e.textContent.trim().split(/\\s+/).length > 6);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {
    x: Math.round(r.left), y: Math.round(r.top + 11),
    w: Math.round(Math.min(r.width, 340)),
    words: el.textContent.trim().split(/\\s+/).slice(0, 5),
  };
`);

if (!prose) {
  check("a paragraph with no anchors was on the board to sweep", false, "none found");
} else {
  await drag("mousePressed", prose.x + 2, prose.y);
  for (let i = 0; i <= 10; i++) await drag("mouseMoved", prose.x + 2 + (prose.w * i) / 10, prose.y);
  await drag("mouseReleased", prose.x + prose.w, prose.y);
  await sleep(600);

  const quoted = await ev(`
    const el = [...document.querySelectorAll('*')].find(e=>e.children.length===0 && /^You marked \u201c/.test(e.textContent.trim()));
    return el ? el.textContent.trim() : null;
  `);
  // Any of the paragraph's opening words appearing in the quote proves the
  // sweep read real text off the page rather than matching an authored span.
  const hit = !!quoted && prose.words.some((w) => quoted.includes(w.replace(/[.,;]$/, "")));
  check("sweeping unanchored prose quotes it rather than reporting nothing",
        hit && !/blank part of the page/i.test(quoted), quoted ?? "no quote at all");
  check("and attributes it to the student's notes",
        await ev("return document.body.innerText.includes('your notes');"));
}

// ────────────────────────────────────────────────────────────────── the quiz
await ask('quiz me');
await sleep(1800);
const quiz = await ev(`
  const dlg = document.querySelector('[role=dialog]');
  if (!dlg) return null;
  const opts = [...dlg.querySelectorAll('button')].map(b=>b.textContent.trim());
  return { text: dlg.innerText.slice(0,120), options: opts.length };
`);
check("asking to be quizzed opens a checkpoint", !!quiz, quiz ? quiz.text.split("\n")[0] : "no dialog");
check("with options to pick from", !!quiz && quiz.options >= 3, quiz ? `${quiz.options} buttons` : "");

if (quiz) {
  await ev(`
    const dlg = document.querySelector('[role=dialog]');
    const opt = [...dlg.querySelectorAll('button')].find(b=>/angle/i.test(b.textContent));
    (opt || dlg.querySelectorAll('button')[0]).click();
    return 1;
  `);
  await sleep(400);
  await ev(`
    const dlg = document.querySelector('[role=dialog]');
    const go = [...dlg.querySelectorAll('button')].find(b=>/Keep going|Show me why/.test(b.textContent));
    go?.click(); return 1;
  `);
  await sleep(1800);
  check("answering it closes the checkpoint",
        await ev("return !document.querySelector('[role=dialog]');"));
  const recorded = await blocks();
  check("and she records the answer on the board",
        recorded.some((b) => b.kind === "callout"),
        JSON.stringify(recorded.map((b) => b.kind)));
}

// ───────────────────────────────────────────────────────── the avatar, drawn
const painted = await ev(`
  const c = document.querySelector('.nty-avatar canvas') || document.querySelector('canvas');
  if (!c) return { found: false };
  const g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let opaque = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 8) opaque++;
  return { found: true, w: c.width, h: c.height, coverage: opaque / (d.length / 4) };
`);
check("the avatar canvas is mounted", painted.found, painted.found ? `${painted.w}x${painted.h}` : "no canvas");
check("the avatar is actually drawn", painted.found && painted.coverage > 0.05,
      painted.found ? `${Math.round(painted.coverage * 100)}% of pixels painted` : "");
check("its background is transparent", painted.found && painted.coverage < 0.9,
      painted.found ? `${Math.round((1 - painted.coverage) * 100)}% clear` : "");

/* "It will talk" is the requirement, so test the mouth, not the element.
   Sample the lower third of the face across a second and check the pixels
   change — a frozen rig and a talking one look identical in a single frame. */
const sampleMouth = `
  const c = document.querySelector('canvas');
  const g = c.getContext('2d');
  const d = g.getImageData(Math.round(c.width*0.32), Math.round(c.height*0.42),
                           Math.round(c.width*0.36), Math.round(c.height*0.22)).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += d[i] + d[i+1] + d[i+2];
  return sum;
`;
await ask('tell me more about why the angle matters so much here');
await sleep(400);
const frames = [];
for (let i = 0; i < 8; i++) { frames.push(await ev(sampleMouth)); await sleep(110); }
check("the avatar animates while speaking", new Set(frames).size >= 3,
      `${new Set(frames).size} distinct frames out of ${frames.length}`);

// ──────────────────────────────────────────────────── layout and scroll room
const widths = await ev(`
  const sheet = document.querySelector('article');
  return { sheet: sheet ? Math.round(sheet.getBoundingClientRect().width) : 0, page: window.innerWidth };
`);
check("the canvas spans the full width", widths.sheet / widths.page > 0.9,
      `${widths.sheet}px of ${widths.page}px`);

/* She stands in front of the page, so content CAN sit behind her. What must be
   true is that the student can always scroll it out from under her. */
const clearance = await ev(`
  const sc = document.querySelector('[class*="scroll"]');
  if (!sc) return { ok: false };
  // scroll-behavior is smooth, so assigning scrollTop animates; force it.
  sc.scrollTo({ top: sc.scrollHeight, behavior: 'instant' });
  await new Promise(r => setTimeout(r, 300));
  // The annotation overlay is absolutely positioned across the whole scroll
  // height, so it must not count as content.
  const kids = [...sc.children].filter(el => getComputedStyle(el).position !== 'absolute');
  const lowest = Math.max(...kids.map(b => b.getBoundingClientRect().bottom));
  const av = document.querySelector('canvas').getBoundingClientRect();
  return { ok: true, lowest: Math.round(lowest), avatarTop: Math.round(av.top),
           scrolled: Math.round(sc.scrollTop),
           range: Math.round(sc.scrollHeight - sc.clientHeight) };
`);
check("content can be scrolled clear of the avatar",
      clearance.ok && clearance.lowest < clearance.avatarTop,
      `scrolled ${clearance.scrolled}px; last line ends at ${clearance.lowest}px, she starts at ${clearance.avatarTop}px`);
check("there is scroll range to do it with", clearance.range > 200, `${clearance.range}px of scroll`);

const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
writeFileSync(`${OUT}/fe_session3.png`, Buffer.from(shot.data, "base64"));

await send("Page.navigate", { url: `http://127.0.0.1:${APP}/` });
await sleep(1400);
const shot2 = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
writeFileSync(`${OUT}/fe_home3.png`, Buffer.from(shot2.data, "base64"));
check("the home screen still renders",
      await ev("return document.body.innerText.includes('Nityam');"));

check("no uncaught page errors", errs.length === 0, errs.slice(0, 3).join(" | "));
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
