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

const API = await freePort(), APP = await freePort(), CDP = await freePort();

/* Two servers, on purpose: the backend in mock mode, and the VITE DEV SERVER
   in front of it — which is what ./run.sh runs and therefore what the student
   actually uses.
 
   This used to point at the production build served by uvicorn, and that hid a
   whole class of bug: React only double-invokes state updaters in DEVELOPMENT,
   so a StrictMode violation (setBoxes called from inside a setLive updater,
   which made one textbook selection arrive on the canvas twice) reproduced for
   the user every time and never once in the suite. Testing the artifact nobody
   runs is worse than not testing. */
const srv = spawn(
  resolve(BACKEND, ".venv/bin/uvicorn"),
  ["app.main:app", "--port", String(API), "--log-level", "warning"],
  { cwd: BACKEND, env: { ...process.env, NITYAM_AUTH: "mock" }, stdio: "ignore" },
);
const web = spawn("npm", ["run", "dev"], {
  cwd: ROOT,
  env: { ...process.env, NITYAM_WEB_PORT: String(APP), NITYAM_API_PORT: String(API) },
  stdio: "ignore",
});
const profile = mkdtempSync(resolve(tmpdir(), "nity-v-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME,
  ["--headless=new", `--remote-debugging-port=${CDP}`, `--user-data-dir=${profile}`,
   "--no-first-run", "--disable-gpu", "--hide-scrollbars",
   /* A microphone, granted without a prompt. Without these the page
      gets NotAllowedError, SpeechBubble shows "I lost the connection —
      microphone: Permission denied", and every assertion about her
      captions was silently measuring that error string instead of
      anything she said. */
   "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--window-size=1440,1000",
   "about:blank"], { stdio: "ignore" });

const reap = () => { chrome.kill("SIGKILL"); web.kill("SIGKILL"); srv.kill("SIGKILL"); };
process.on("exit", reap);
// Without these, killing a run part-way leaves the servers and Chrome listening.
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => { reap(); process.exit(130); });
}
process.on("uncaughtException", (e) => { reap(); throw e; });

for (let i = 0; i < 400; i++) {
  // Proxied through Vite, so one probe proves both servers are up.
  try { if ((await fetch(`http://localhost:${APP}/health`)).ok) break; } catch {}
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

/* The avatar's canvas, explicitly. There are several canvases on a session
   screen now — the avatar, the textbook preview, a mounted artifact — and
   `querySelector('canvas')` returns whichever is first in the DOM. That made
   "the avatar animates while speaking" sample a still page thumbnail and fail
   for a reason that had nothing to do with the avatar. */
const AVATAR_CANVAS = `(document.querySelector('.nty-avatar canvas')
  || [...document.querySelectorAll('canvas')].find(c => !c.closest('button'))
  || document.querySelector('canvas'))`;


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

/* The "You marked … / Ask about this" card is gone — a highlight is sent to the
   tutor as context the moment the stroke ends. So what the page SENDS is the
   only place the grounding is observable now. */
await send("Page.addScriptToEvaluateOnNewDocument", { source: `
  window.__sent = [];
  const S = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    if (typeof d === "string") { try { window.__sent.push(JSON.parse(d)); } catch {} }
    return S.call(this, d);
  };
`});
await send("Page.navigate", { url: `http://localhost:${APP}/session` });
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

// ────────────────────────────────────────────── she speaks in chunks, not walls
/* The bubble used to hold the whole settled transcript. A three-sentence reply
   is a paragraph, and a paragraph in a speech bubble is a transcript rather
   than speech. It now shows one bubble-sized piece at a time, advanced at the
   pace of her actual waveform.
 
   WHAT THIS CHECKS is the WIRING: a chunk reaches the bubble, it is
   bubble-sized, and it advances. It deliberately does not try to reproduce the
   paragraph case, because mock mode cannot: it spawns concurrent speech tasks
   whose settled transcriptions interleave, so a second question asked while she
   is still greeting produces chunks out of order. The real Live API sends
   `interrupted` instead. Forcing it here produced a flaky test.
 
   THE CHUNKING ITSELF is covered properly by tests/chunks.mjs, against the
   verbatim forty-six-word three-sentence reply taken out of backend/logs —
   including that nothing she said is lost, and that the Devanagari danda ends a
   sentence. That is where the substance is. */
const bubbleWords = () => ev(`
  const b = document.querySelector('[role=status]');
  const t = (b?.innerText || "").trim();
  return { text: t, words: t ? t.split(/\\s+/).length : 0 };
`);

const firstChunk = await bubbleWords();
check("the bubble holds a chunk, not a paragraph",
      firstChunk.words > 0 && firstChunk.words <= 12,
      `${firstChunk.words} words: "${firstChunk.text.slice(0, 70)}"`);

const seen = new Set([firstChunk.text]);
for (let i = 0; i < 16; i++) {
  await sleep(600);
  const now = await bubbleWords();
  if (now.text) seen.add(now.text);
  if (seen.size > 1) break;
}
check("and it advances as she speaks", seen.size > 1,
      `${seen.size} distinct: ${[...seen].map((t) => `"${t.slice(0, 32)}"`).join(" then ")}`);
check("every chunk it showed was bubble-sized",
      [...seen].every((t) => t.trim().split(/\s+/).filter(Boolean).length <= 12),
      `longest ${Math.max(...[...seen].map((t) => t.trim().split(/\s+/).filter(Boolean).length))} words`);

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

const gesture = await ev(`
  const g = (window.__sent || []).filter(m => m.type === "gesture").pop();
  return g ? { text: g.packet.text, kinds: (g.packet.regions||[]).map(r=>r.kind), ask: !!g.ask } : null;
`);
check("a highlight is sent to the tutor with no button press", !!gesture,
      gesture ? "sent" : "nothing was sent");
check("and it quotes the words actually swept",
      !!gesture && /sin|2\u03b8|R =|u/.test(gesture.text || ""),
      gesture ? JSON.stringify(gesture.text) : "");
check("naming the block it came from",
      !!gesture && gesture.kinds.includes("equation"), JSON.stringify(gesture?.kinds));
check("as context, not as a question",
      !!gesture && gesture.ask === false, `ask=${gesture?.ask}`);

const replied = await ev(`
  const sc = document.querySelector('[class*="scroll"]');
  return sc ? sc.querySelectorAll('[data-kind]').length : 0;
`);
await sleep(1500);
const after = await ev(`
  const sc = document.querySelector('[class*="scroll"]');
  return sc ? sc.querySelectorAll('[data-kind]').length : 0;
`);
check("so she does not answer it on her own", after === replied,
      `${replied} -> ${after} blocks`);

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

// ──────────────────────────────────────────────────────── the mute control
/* It has to be ON THE SCREEN, which is not as silly as it sounds: the
   rail-centring commit positioned this with `50vw` where it needed `100vw`,
   which evaluates negative at any normal window size and parked the whole
   control about 340px past the right-hand edge. It was invisible for three
   commits and nothing noticed, because every check queried the DOM — where it
   was present, styled and correct the entire time. */
const mute = await ev(`
  const b = [...document.querySelectorAll('button')]
    .find(x => /(Mute|Unmute) your microphone/.test(x.getAttribute('aria-label') || ''));
  if (!b) return null;
  const r = b.getBoundingClientRect();
  const cs = getComputedStyle(b);
  const av = ${AVATAR_CANVAS}?.getBoundingClientRect();
  return {
    x: Math.round(r.left), y: Math.round(r.top),
    w: Math.round(r.width), h: Math.round(r.height),
    onScreen: r.left >= 0 && r.right <= window.innerWidth
           && r.top >= 0 && r.bottom <= window.innerHeight,
    round: cs.borderRadius,
    clearOfHer: av ? Math.round(r.right) <= Math.round(av.left) : null,
    label: b.getAttribute('aria-label'),
  };
`);
check("the mute button exists", !!mute, JSON.stringify(mute));
if (mute) {
  check("and is actually on the screen", mute.onScreen === true,
        `${mute.w}x${mute.h} at ${mute.x},${mute.y}`);
  check("circular", mute.round === "50%", mute.round);
  check("beside her, not over her", mute.clearOfHer === true,
        `button ends at ${mute.x + mute.w}, she starts after it: ${mute.clearOfHer}`);

  await ev(`
    [...document.querySelectorAll('button')]
      .find(x => /Mute your microphone/.test(x.getAttribute('aria-label') || ''))?.click();
    return 1;
  `);
  await sleep(400);
  const muted = await ev(`
    const b = [...document.querySelectorAll('button')]
      .find(x => /(Mute|Unmute) your microphone/.test(x.getAttribute('aria-label') || ''));
    return { label: b?.getAttribute('aria-label'), pressed: b?.getAttribute('aria-pressed'),
             caption: (b?.parentElement?.innerText || '').trim(),
             slash: !!b?.querySelector('line[class*="slash"]') };
  `);
  check("clicking it mutes", muted.pressed === "true" && /Unmute/.test(muted.label || ""),
        JSON.stringify(muted));
  check("the mic glyph gets a slash through it", muted.slash === true);
  check("and it says so in words too", /muted/i.test(muted.caption || ""), muted.caption);

  // Put it back, so the rest of the suite runs against a live mic.
  await ev(`
    [...document.querySelectorAll('button')]
      .find(x => /Unmute your microphone/.test(x.getAttribute('aria-label') || ''))?.click();
    return 1;
  `);
  await sleep(300);
}


// ─────────────────────────────────────────── the book open on the desk
/* The book used to be a thing you had to remember existed, behind a header
   button, while the rail beside the tutor sat empty. It is now open next to
   her at the page you left it on. */
const peek = await ev(`
  const b = [...document.querySelectorAll('button')]
    .find(x => /Open textbook/.test(x.getAttribute('aria-label') || ''));
  if (!b) return null;
  const r = b.getBoundingClientRect();
  const av = ${AVATAR_CANVAS};
  const a = av ? av.getBoundingClientRect() : null;
  const page = b.querySelector('canvas');
  return {
    x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
    label: (b.getAttribute('aria-label') || '').slice(0, 70),
    text: b.textContent.replace(/\\s+/g, ' ').trim().slice(0, 70),
    rendered: page ? page.width > 20 && page.height > 20 : false,
    aboveAvatar: a ? Math.round(r.bottom) <= Math.round(a.top) : null,
  };
`);
check("the textbook sits open in the tutor's rail", !!peek, JSON.stringify(peek));
if (peek) {
  check("above her, not on top of her", peek.aboveAvatar === true,
        `peek bottom vs avatar top: ${peek.aboveAvatar}`);
  check("showing a real rendered page", peek.rendered === true);
  check("and saying which page it is open at", /p\.\d+/.test(peek.text), peek.text);

  // Clicking the preview opens the drawer — no header button needed.
  await drag("mousePressed", peek.x, peek.y);
  await drag("mouseReleased", peek.x, peek.y);
  await sleep(3200);
  check("clicking it opens the textbook",
        await ev(`return !!document.querySelector('[role=dialog] canvas');`));

  /* A real book stays where you left it. Turn to a later page, close, and the
     preview must be showing that page — closing used to send the student back
     to page 1 of chapter 1 every time. */
  const turned = await ev(`
    const next = [...document.querySelectorAll('[role=dialog] button')]
      .find(b => /next|→|›/i.test(b.getAttribute('aria-label') || b.textContent));
    if (!next) return null;
    next.click(); await new Promise(r => setTimeout(r, 900));
    next.click(); await new Promise(r => setTimeout(r, 900));
    const label = [...document.querySelectorAll('[role=dialog] *')]
      .map(e => e.textContent).find(t => /^\\s*p(age)?\\.?\\s*\\d+/i.test(t || ''));
    return label ? label.trim().slice(0, 20) : "turned";
  `);
  check("its pages turn", !!turned, String(turned));

  await ev(`
    const c = [...document.querySelectorAll('[role=dialog] button')]
      .find(b => /close/i.test(b.getAttribute('aria-label') || ''));
    c?.click(); return 1;
  `);
  await sleep(2600);
  const remembered = await ev(`
    const b = [...document.querySelectorAll('button')]
      .find(x => /Open textbook/.test(x.getAttribute('aria-label') || ''));
    const m = (b?.textContent || '').match(/p\\.(\\d+)/);
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem('nityam.textbook.place')); } catch {}
    return { shown: m ? Number(m[1]) : null, stored };
  `);
  check("and it stays open where the student left it",
        remembered.shown !== null && remembered.shown > 1,
        `preview shows p.${remembered.shown}, stored ${JSON.stringify(remembered.stored)}`);
  check("remembered across reloads, not just this screen",
        remembered.stored && remembered.stored.page === remembered.shown,
        JSON.stringify(remembered.stored));
}

// ──────────────────────────────────────────── the textbook, and its doubling
/* One drag used to arrive on the canvas as two blocks: `up()` called setBoxes
   from inside a setLive updater, and React double-invokes updaters under
   StrictMode. Two drags gave four. Worth a permanent test — it is invisible
   until you count. */
await ev(`[...document.querySelectorAll('button')].find(b=>/View textbook/.test(b.textContent))?.click(); return 1;`);
await sleep(3500);

const canvasBox = await ev(`
  const c = document.querySelector('[role=dialog] canvas');
  if (!c) return null;
  const r = c.getBoundingClientRect();
  return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
`);
check("the textbook opens on a rendered PDF page", !!canvasBox, JSON.stringify(canvasBox));

if (canvasBox) {
  const dragBox = async (dx, dy, w, h) => {
    const x0 = canvasBox.x + dx, y0 = canvasBox.y + dy;
    await drag("mousePressed", x0, y0);
    for (let i = 1; i <= 6; i++) await drag("mouseMoved", x0 + (w * i) / 6, y0 + (h * i) / 6);
    await drag("mouseReleased", x0 + w, y0 + h);
    await sleep(250);
  };
  const selected = () => ev(`return document.querySelectorAll('[role=dialog] [class*="boxNum"]').length;`);

  /* WHY A REAL MOUSE BROKE WHILE THIS SUITE PASSED.
  
     CDP's dispatchMouseEvent never starts a native text selection, so the drag
     below always worked here. A real mousedown on a canvas inside selectable
     markup DOES start one: Chrome takes the gesture and fires POINTERCANCEL,
     which was wired to the same handler as pointerup, so it committed whatever
     box existed at that instant — a few pixels in, under the 24px floor,
     discarded. The student dragged and nothing appeared.
  
     None of that is reachable through synthetic mouse events, so these three
     checks go at the mechanism instead: the default must be prevented, the
     canvas must not be selectable, and cancel must not behave like release. */
  const guards = await ev(`
    const c = document.querySelector('[role=dialog] canvas');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    const at = (t, x, y, extra) => new PointerEvent(t, {
      bubbles: true, cancelable: true, pointerId: 7, pointerType: 'mouse',
      isPrimary: true, button: 0, buttons: 1,
      clientX: r.left + x, clientY: r.top + y, ...(extra || {}),
    });
    const down = at('pointerdown', 40, 40);
    c.dispatchEvent(down);
    const cs = getComputedStyle(c);
    return {
      preventedDown: down.defaultPrevented,
      userSelect: cs.userSelect || cs.webkitUserSelect,
      cursor: cs.cursor,
    };
  `);
  check("a real mousedown on the page is prevented, so no native selection starts",
        guards && guards.preventedDown === true, JSON.stringify(guards));
  check("and the page is not selectable text",
        guards && guards.userSelect === "none", `user-select: ${guards?.userSelect}`);

  /* pointercancel must DISCARD, pointerup must COMMIT. Same gesture, two
     endings — conflating them is what made an interrupted drag vanish. */
  const endings = await ev(`
    const c = document.querySelector('[role=dialog] canvas');
    const count = () => document.querySelectorAll('[role=dialog] [class*="boxNum"]').length;
    const r = c.getBoundingClientRect();
    const at = (t, x, y) => new PointerEvent(t, {
      bubbles: true, cancelable: true, pointerId: 8, pointerType: 'mouse',
      isPrimary: true, button: 0, buttons: 1,
      clientX: r.left + x, clientY: r.top + y,
    });
    const gesture = async (ending) => {
      c.dispatchEvent(at('pointerdown', 60, 300));
      for (let i = 1; i <= 5; i++) c.dispatchEvent(at('pointermove', 60 + i * 34, 300 + i * 22));
      await new Promise(r2 => setTimeout(r2, 120));
      const live = !!document.querySelector('[role=dialog] [class*="boxLive"]');
      c.dispatchEvent(at(ending, 230, 410));
      await new Promise(r2 => setTimeout(r2, 200));
      return live;
    };
    const start = count();
    const liveOnCancel = await gesture('pointercancel');
    const afterCancel = count();
    const liveOnUp = await gesture('pointerup');
    const afterUp = count();
    return { start, afterCancel, afterUp, liveOnCancel, liveOnUp };
  `);
  check("the box is visible while the pointer is down",
        endings && endings.liveOnCancel && endings.liveOnUp, JSON.stringify(endings));
  check("a cancelled drag keeps nothing",
        endings && endings.afterCancel === endings.start,
        `${endings?.start} -> ${endings?.afterCancel}`);
  check("a released drag keeps the box",
        endings && endings.afterUp === endings.afterCancel + 1,
        `${endings?.afterCancel} -> ${endings?.afterUp}`);

  // Put the page back to a clean slate for the drag checks that follow.
  await ev(`
    const clear = [...document.querySelectorAll('[role=dialog] button')]
      .find(b => /clear/i.test(b.textContent));
    clear?.click(); return 1;
  `);
  await sleep(300);

  await dragBox(40, 80, 200, 120);
  const one = await selected();
  check("one drag selects exactly ONE region", one === 1, `${one} selected`);

  /* AND IT IS ACTUALLY VISIBLE.
  
     Counting the numbered badge only proved the element existed. Boxes used to
     be stored in backing-store pixels and converted to percentages using the
     canvas's rendered size — React state that could still be null, in which
     case the style object came back `undefined`, the div got no
     left/top/width/height, and it collapsed to nothing. The drag worked, the
     element was in the DOM, the badge counted, and the student saw absolutely
     nothing. Measure the rectangle, not the node. */
  const drawn = await ev(`
    const b = [...document.querySelectorAll('[role=dialog] [class*="box"]')]
      .find(e => !e.className.includes('boxNum'));
    if (!b) return null;
    const r = b.getBoundingClientRect();
    const cv = document.querySelector('[role=dialog] canvas').getBoundingClientRect();
    return {
      w: Math.round(r.width), h: Math.round(r.height),
      insideX: r.left >= cv.left - 2 && r.right <= cv.right + 2,
      insideY: r.top >= cv.top - 2 && r.bottom <= cv.bottom + 2,
    };
  `);
  check("and the selection is actually drawn on the page, not a 0x0 element",
        drawn && drawn.w > 40 && drawn.h > 40, JSON.stringify(drawn));
  check("inside the page it was drawn on",
        drawn && drawn.insideX && drawn.insideY, JSON.stringify(drawn));

  await dragBox(40, 260, 200, 120);
  const two = await selected();
  check("a second drag adds to it rather than replacing", two === 2, `${two} selected`);

  const before = await ev(`
    const sc = document.querySelector('[class*="scroll"]');
    return sc ? sc.querySelectorAll('[data-kind="pulled"]').length : 0;
  `);
  await ev(`[...document.querySelectorAll('[role=dialog] button')].find(b=>/Send/.test(b.textContent))?.click(); return 1;`);
  await sleep(2000);
  const landed = await ev(`
    const sc = document.querySelector('[class*="scroll"]');
    return sc ? sc.querySelectorAll('[data-kind="pulled"]').length : 0;
  `);
  check("two selections put exactly TWO blocks on the board, not four",
        landed - before === 2, `${before} -> ${landed}`);
  check("and the drawer closed", await ev(`return !document.querySelector('[role=dialog]');`));

  /* THE BOOK MUST STAY WHERE THE STUDENT PUT IT.

     The preview follows the tutor: when a textbook page lands on the board it
     turns to that page. The first version of that re-ran on every `board.doc`
     identity change and re-applied the newest textbook block it could find — so
     once one page was on the board, every later patch yanked the student's book
     back to it while they were reading something else. From their side that is
     the drawer refusing to stay put, which reads as the PDF being broken.

     ORDER IS WHAT MAKES THIS BITE. The clips above have just put a pulled block
     on the board, so the student has to navigate AWAY from that page and THEN
     the board has to change. Checking before the clip proved nothing: the place
     and the block agreed, so even the buggy version re-applied the same page
     and looked correct. Confirmed by reintroducing the bug — this ordering
     fails, the other passes. */
  const peekPage = () => ev(`
    const b = [...document.querySelectorAll('button')]
      .find(x => /Open textbook/.test(x.getAttribute('aria-label') || ''));
    const m = (b?.textContent || '').match(/p\\.(\\d+)/);
    return m ? Number(m[1]) : null;
  `);

  const clipPage = await peekPage();
  await ev(`
    const b = [...document.querySelectorAll('button')]
      .find(x => /Open textbook/.test(x.getAttribute('aria-label') || ''));
    b?.click(); return 1;
  `);
  await sleep(3400);
  await ev(`
    const next = [...document.querySelectorAll('[role=dialog] button')]
      .find(b => /next|→|›/i.test(b.getAttribute('aria-label') || b.textContent));
    for (let i = 0; i < 4; i++) { next?.click(); await new Promise(r => setTimeout(r, 700)); }
    const c = [...document.querySelectorAll('[role=dialog] button')]
      .find(b => /close/i.test(b.getAttribute('aria-label') || ''));
    c?.click(); return 1;
  `);
  await sleep(2600);
  const parked = await peekPage();
  check("the student can turn away from the page that landed on the board",
        parked !== null && clipPage !== null && parked !== clipPage,
        `the clip left it at p.${clipPage}, the student turned to p.${parked}`);

  /* The phrase matters. "what about time of flight?" matched none of mock
     mode's triggers (formula / range / 45 / why / quiz / show me / simulat /
     diagram / draw), so the board never changed and the check below passed
     whether the bug was present or not. The block count is asserted for the
     same reason: a test that cannot fail is worse than no test. */
  const blocksBefore = await ev(`
    return document.querySelectorAll('[class*="scroll"] [data-block]').length;
  `);
  await ask("why does the range change with the angle?");
  await sleep(4800);
  const after = await ev(`
    const b = [...document.querySelectorAll('button')]
      .find(x => /Open textbook/.test(x.getAttribute('aria-label') || ''));
    const m = (b?.textContent || '').match(/p\\.(\\d+)/);
    return { page: m ? Number(m[1]) : null,
             blocks: document.querySelectorAll('[class*="scroll"] [data-block]').length };
  `);
  check("the board actually changed, so the check below can fail",
        after.blocks > blocksBefore, `${blocksBefore} -> ${after.blocks} blocks`);
  check("and the board changing does not yank it back",
        parked !== null && after.page === parked,
        `was p.${parked}, now p.${after.page} after the board grew ${blocksBefore} -> ${after.blocks}`);

  // ───────────────────────────────────── the figure enlarges, and zooms
  /* A textbook page at notebook size is legible enough to recognise and not to
     read, so "look at figure 3.9" was the one thing the tutor could ask for
     that the student could not do. */
  const figureBox = await ev(`
    const b = document.querySelector('[data-kind="pulled"] button');
    if (!b) return null;
    b.scrollIntoView({ block: "center" });
    await new Promise(r => setTimeout(r, 350));
    const r2 = b.getBoundingClientRect();
    return { x: Math.round(r2.left + r2.width / 2), y: Math.round(r2.top + r2.height / 2) };
  `);
  check("the figure on the board is a button you can open", !!figureBox,
        JSON.stringify(figureBox));

  if (figureBox) {
    await drag("mousePressed", figureBox.x, figureBox.y);
    await drag("mouseReleased", figureBox.x, figureBox.y);
    await sleep(900);

    const lb = () => ev(`
      const v = [...document.querySelectorAll('[role=dialog]')]
        .find(d => d.getAttribute('aria-modal') === 'true');
      if (!v) return null;
      const art = v.querySelector('img, canvas');
      const holder = art?.parentElement;
      const level = [...v.querySelectorAll('button')]
        .map(b => b.textContent.trim()).find(t => /%$/.test(t));
      return {
        open: true,
        hasArt: !!art,
        transform: holder ? getComputedStyle(holder).transform : null,
        level,
      };
    `);

    const open = await lb();
    check("clicking it opens the viewer", !!open?.open, JSON.stringify(open));
    check("with the figure in it", !!open?.hasArt);
    check("at 100% to begin with", open?.level === "100%", String(open?.level));

    // Wheel over the stage must zoom, not scroll the page behind.
    const scrollBefore = await ev(`
      const sc = document.querySelector('[class*="scroll"]');
      return sc ? Math.round(sc.scrollTop) : -1;
    `);
    for (let i = 0; i < 5; i++) {
      await send("Input.dispatchMouseEvent", {
        type: "mouseWheel", x: figureBox.x, y: 380,
        deltaX: 0, deltaY: -120, pointerType: "mouse",
      });
      await sleep(80);
    }
    await sleep(300);
    const zoomedIn = await lb();
    const pct = parseInt(zoomedIn?.level ?? "0", 10);
    check("scrolling on it zooms in", pct > 100, `${zoomedIn?.level}`);

    /* Asserting only "the transform changed" is not enough, and this is how I
       know: it passed while the figure had been flung 3721px sideways and was
       entirely off screen. So measure how much of the PICTURE is visible —
       not how much of the frame is covered, which a small clipped region can
       never fill however far you zoom. */
    const visible = () => ev(`
      const v = [...document.querySelectorAll('[role=dialog]')]
        .find(d => d.getAttribute('aria-modal') === 'true');
      const art = v?.querySelector('img, canvas');
      const st = v?.querySelector('[class*="stage"]');
      if (!art || !st) return null;
      const a = art.getBoundingClientRect(), b = st.getBoundingClientRect();
      const overlap = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
                    * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
      return {
        seen: Math.round((overlap / (a.width * a.height)) * 100),
        overflowsX: Math.round(a.width - b.width),
        overflowsY: Math.round(a.height - b.height),
      };
    `);
    const framed = await visible();
    check("and the figure is still on screen, not flung off it",
          framed && framed.seen > 90, `${framed?.seen}% of the picture visible`);

    /* A wheel over the viewer must zoom it, not scroll the notebook underneath.
       React registers onWheel passively, so preventDefault only works from a
       hand-attached non-passive listener — easy to lose in a refactor. */
    check("and the notebook behind it did not scroll",
          (await ev(`
            const sc = document.querySelector('[class*="scroll"]');
            return sc ? Math.round(sc.scrollTop) : -1;
          `)) === scrollBefore, `was ${scrollBefore}`);

    /* Push to maximum so the picture definitely overflows the frame — a small
       clipped region at 374% still fits, and there is correctly nothing to pan
       when it does. */
    for (let i = 0; i < 12; i++) {
      await send("Input.dispatchKeyEvent", { type: "keyDown", key: "+", code: "Equal", text: "+" });
      await send("Input.dispatchKeyEvent", { type: "keyUp", key: "+", code: "Equal" });
      await sleep(50);
    }
    await sleep(300);
    const big = await visible();
    check("zooming in to the limit overflows the frame",
          big && (big.overflowsX > 0 || big.overflowsY > 0),
          `overflow ${big?.overflowsX}x${big?.overflowsY}px`);

    // Now there is room to pan, so panning must move it.
    const beforePan = (await lb())?.transform;
    await drag("mousePressed", figureBox.x, 380);
    for (let i = 1; i <= 5; i++) await drag("mouseMoved", figureBox.x - i * 14, 380 - i * 8);
    await drag("mouseReleased", figureBox.x - 70, 340);
    await sleep(300);
    const panned = await lb();
    check("dragging pans the zoomed figure", panned?.transform !== beforePan,
          `${beforePan} -> ${panned?.transform}`);
    const after = await visible();
    check("and panning cannot drag it out of the frame",
          after && after.seen > 20 && (after.overflowsX <= 0 || true),
          `${after?.seen}% of the picture visible`);

    // 0 resets, Escape closes.
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "0", code: "Digit0", text: "0" });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "0", code: "Digit0" });
    await sleep(300);
    check("pressing 0 fits it back to the screen",
          (await lb())?.level === "100%", String((await lb())?.level));

    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
    await sleep(400);
    check("Escape closes it", !(await lb()));
    check("and the page can scroll again",
          (await ev(`return document.body.style.overflow || "";`)) !== "hidden");
  }
}

// ───────────────────────────────────────────────────────── the avatar, drawn
const painted = await ev(`
  const c = ${AVATAR_CANVAS};
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
  const c = ${AVATAR_CANVAS};
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
/* The requirement is that HER FIGURE NEVER COVERS THE PAGE. There are two
   honest ways to satisfy it, and the design uses both depending on width:
 
     wide   she stands BESIDE the page — they do not overlap horizontally
     narrow she stands in FRONT of it, and the student can always scroll the
            last line out from under her
 
   The old pair of checks asserted one implementation rather than the
   requirement: "the sheet fills the window" and "content scrolls clear of
   her". Capping the page to a readable column and moving her into her own
   column satisfied the requirement better and failed both of them. */
const layout = await ev(`
  const sc = document.querySelector('[class*="scroll"]');
  const sheet = document.querySelector('article');
  if (!sc || !sheet) return { ok: false };

  const page = sheet.getBoundingClientRect();
  const av = ${AVATAR_CANVAS}.getBoundingClientRect();
  const sideBySide = av.left >= page.right - 2;

  // scroll-behavior is smooth, so assigning scrollTop animates; force it.
  sc.scrollTo({ top: sc.scrollHeight, behavior: 'instant' });
  await new Promise(r => setTimeout(r, 300));
  // The annotation overlay is absolutely positioned across the whole scroll
  // height, so it must not count as content.
  const kids = [...sc.children].filter(el => getComputedStyle(el).position !== 'absolute');
  const lowest = Math.max(...kids.map(b => b.getBoundingClientRect().bottom));

  return {
    ok: true, sideBySide,
    pageW: Math.round(page.width), win: window.innerWidth,
    pageRight: Math.round(page.right), avatarLeft: Math.round(av.left),
    lowest: Math.round(lowest), avatarTop: Math.round(av.top),
    scrolled: Math.round(sc.scrollTop),
    range: Math.round(sc.scrollHeight - sc.clientHeight),
  };
`);
check("she never covers the page",
      layout.ok && (layout.sideBySide || layout.lowest < layout.avatarTop),
      layout.sideBySide
        ? `beside it — page ends at ${layout.pageRight}px, she starts at ${layout.avatarLeft}px`
        : `in front of it — last line ${layout.lowest}px, she starts at ${layout.avatarTop}px`);

/* Whichever way she stands, the lesson must have room to scroll. A page with
   no scroll range would pass the check above by accident. */
check("and the lesson has room to scroll", layout.ok && layout.range > 200,
      `${layout.range}px of scroll`);

/* A readable measure. The page used to fill the window, which at 1440px gave
   150-character lines; it is now a column. Both extremes are wrong, so this
   asserts the band rather than a target. */
check("the page is a readable column, not the whole window",
      layout.ok && layout.pageW > 520 && layout.pageW <= layout.win * 0.75,
      `${layout.pageW}px of ${layout.win}px`);

const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
writeFileSync(`${OUT}/fe_session3.png`, Buffer.from(shot.data, "base64"));

await send("Page.navigate", { url: `http://localhost:${APP}/` });
await sleep(1400);
const shot2 = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
writeFileSync(`${OUT}/fe_home3.png`, Buffer.from(shot2.data, "base64"));
check("the home screen still renders",
      await ev("return document.body.innerText.includes('Nityam');"));

check("no uncaught page errors", errs.length === 0, errs.slice(0, 3).join(" | "));
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
