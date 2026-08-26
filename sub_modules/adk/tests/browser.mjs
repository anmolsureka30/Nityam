// Drives the real React app in headless Chrome, against the mock backend.
//
// Chrome's fake media device gives us a microphone without a human, so the
// whole pipeline runs: getUserMedia -> AudioWorklet -> PCM16 -> WebSocket ->
// mock session -> event JSON -> AudioWorklet playback. Talks to Chrome over
// the DevTools protocol directly; no Puppeteer, nothing to install.
//
//   node tests/browser.mjs [--keep-screenshot]
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APP_PORT = await freePort();
const CDP_PORT = await freePort();
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Fixed ports collide with a server the previous suite has not finished
// releasing, which shows up as a mystifying timeout. Ask the OS for a free one.
import { createServer } from "node:net";
async function freePort() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.unref();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}


// A test that throws must not leave a server holding a port. SIGKILL rather
// than SIGTERM, and cover the signal paths, not just normal exit.
function reap(...children) {
  let done = false;
  const kill = () => {
    if (done) return;
    done = true;
    for (const child of children) {
      try { child.kill("SIGKILL"); } catch { /* already gone */ }
    }
  };
  process.on("exit", kill);
  process.on("SIGINT", () => { kill(); process.exit(130); });
  process.on("SIGTERM", () => { kill(); process.exit(143); });
  process.on("uncaughtException", (err) => { kill(); console.error(err); process.exit(1); });
  return kill;
}

let passed = 0;
const check = (name, fn) => { fn(); passed++; console.log(`  ok  ${name}`); };

async function until(predicate, { timeout = 15000, what = "condition" } = {}) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    last = await predicate();
    if (last) return last;
    await sleep(150);
  }
  throw new Error(`timed out waiting for ${what} (last saw ${JSON.stringify(last)})`);
}

// --------------------------------------------------------------- processes

const server = spawn(
  resolve(ROOT, ".venv/bin/uvicorn"),
  ["--app-dir", "backend", "main:app", "--port", String(APP_PORT), "--log-level", "warning"],
  { cwd: ROOT, env: { ...process.env, NITYAM_AUTH: "mock" }, stdio: "ignore" }
);

const profile = mkdtempSync(resolve(tmpdir(), "nityam-chrome-"));
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${CDP_PORT}`,
  `--user-data-dir=${profile}`,
  "--no-first-run",
  "--disable-gpu",
  "--window-size=1280,860",
  // a synthetic microphone, auto-granted
  "--use-fake-device-for-media-stream",
  "--use-fake-ui-for-media-stream",
  "--autoplay-policy=no-user-gesture-required",
  "about:blank",
], { stdio: "ignore" });

reap(chrome, server);

// --------------------------------------------------------------- cdp

async function cdpTarget() {
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(150);
  }
  throw new Error("chrome devtools never came up");
}

let nextId = 1;
const pending = new Map();
const socket = new WebSocket(await cdpTarget());
await new Promise((res, rej) => { socket.onopen = res; socket.onerror = rej; });
socket.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  const waiter = pending.get(payload.id);
  if (waiter) {
    pending.delete(payload.id);
    payload.error ? waiter.reject(new Error(payload.error.message)) : waiter.resolve(payload.result);
  }
};

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });

async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {
    expression: `(() => { ${expression} })()`,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description ?? "page threw");
  }
  return result.result.value;
}

const text = (selector) =>
  evaluate(`return document.querySelector(${JSON.stringify(selector)})?.textContent ?? null;`);
const click = (selector) =>
  evaluate(`document.querySelector(${JSON.stringify(selector)})?.click(); return true;`);

// --------------------------------------------------------------- the test

await until(async () => {
  try { return (await fetch(`http://127.0.0.1:${APP_PORT}/health`)).ok; } catch { return false; }
}, { what: "backend" });

await send("Page.enable");
await send("Runtime.enable");

// Collect page errors: a broken worklet URL or a bad import shows up here and
// nowhere else.
const consoleErrors = [];
socket.addEventListener("message", (message) => {
  const payload = JSON.parse(message.data);
  if (payload.method === "Runtime.exceptionThrown") {
    consoleErrors.push(payload.params.exceptionDetails.text);
  }
});

await send("Page.navigate", { url: `http://127.0.0.1:${APP_PORT}/` });
await until(() => evaluate("return !!document.querySelector('.orb');"), { what: "app to mount" });

const shell = { title: await text(".brand h1"), orb: await text(".orb") };
check("the app renders its shell", () => {
  assert.match(shell.title, /Nityam/);
  assert.match(shell.orb, /Start session/);
});

// --- connect ------------------------------------------------------------

await click(".orb");
await until(() => evaluate("return document.querySelector('.dot')?.classList.contains('on');"),
  { what: "websocket to connect" });

const modeBadge = await text(".badge.warn");
check("clicking the orb opens the socket and the server announces its mode", () => {
  assert.match(modeBadge, /mock mode/);
});

// --- greeting -----------------------------------------------------------

// The caption must stream while she is still talking, not appear only once the
// turn ends. Catching the live bubble mid-turn is the assertion that proves it.
const streaming = await until(
  () => evaluate("return document.querySelector('.turn.model.live.speaking .turn-text')?.textContent?.trim() || null;"),
  { what: "a caption while the tutor is still speaking" }
);
check("captions stream during the turn, not after it", () => {
  assert.ok(streaming.length > 0);
});

const firstAgent = { who: await text(".agent .who"), voice: await text(".agent .voice") };
check("the greeting is attributed to the tutor agent, with its own voice", () => {
  assert.match(firstAgent.who, /Tutor/);
  assert.match(firstAgent.voice, /Leda/);
});

const greeting = await until(
  () => evaluate("const t=document.querySelectorAll('.turn.model:not(.live) .turn-text'); return t.length ? t[t.length-1].textContent : null;"),
  { what: "the finished greeting caption" }
);
check("the finished turn settles into a normal bubble", () => {
  assert.match(greeting, /Nityam/);
});

check("a turn is one bubble, and no sentence is printed twice", () => {
  // The consolidated transcription repeats the whole sentence the partials
  // already spelled out; appending both is the bug. And multi-sentence turns
  // must not fragment into a bubble per sentence.
  assert.match(greeting, /Namaste/);
  assert.equal(
    (greeting.match(/Namaste/gi) ?? []).length,
    1,
    `"Namaste" appears more than once: ${greeting}`
  );
  assert.ok(
    /Nityam/.test(greeting),
    `both sentences should share one bubble, got: ${greeting}`
  );
});

// --- audio actually plays ----------------------------------------------

// Both worklets are fetched by URL at runtime, and a 404 there is the classic
// silent failure: no error in the UI, just no sound.
const workletResponses = await Promise.all(
  ["/pcm-player-processor.js", "/pcm-recorder-processor.js"].map(async (path) => {
    const response = await fetch(`http://127.0.0.1:${APP_PORT}${path}`);
    return { path, ok: response.ok, body: await response.text() };
  })
);
check("both AudioWorklet modules are served where the client asks for them", () => {
  for (const response of workletResponses) {
    assert.ok(response.ok, `${response.path} did not 200`);
    assert.match(response.body, /registerProcessor/, `${response.path} is not a worklet`);
  }
});

const banner = await evaluate("return document.querySelector('.error')?.textContent ?? null;");
check("no error banner is shown", () => {
  assert.equal(banner, null);
});

// --- agent transfer, driven through the UI ------------------------------

await evaluate(`
  const input = document.querySelector('.composer input');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(input, 'quiz me');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('.composer button').click();
  return true;
`);

const handoff = await until(
  () => evaluate("return document.querySelector('.turn.system .system')?.textContent ?? null;"),
  { what: "handoff notice" }
);
check("the UI shows the handoff between agents", () => {
  assert.match(handoff, /quiz_master/);
});

await until(() => evaluate("return document.querySelector('.agent .who')?.textContent;")
  .then((v) => (/Quiz master/.test(v ?? "") ? v : null)), { what: "agent badge to switch" });
const secondVoice = await text(".agent .voice");
check("the agent badge follows the transfer, voice and all", () => {
  assert.match(secondVoice, /Puck/);
});

const score = await until(
  () => evaluate("return document.querySelector('.card-value')?.textContent ?? null;"),
  { what: "score card from record_answer" }
);
check("a tool result reaches the UI", () => {
  assert.match(score, /\d+\s*\/\s*\d+/);
});

// --- microphone --------------------------------------------------------

await click(".orb");
await until(() => evaluate("return document.querySelector('.orb')?.classList.contains('hot');"),
  { what: "microphone to open" });
const orbClasses = await evaluate("return document.querySelector('.orb').className;");
check("the microphone opens and the orb reflects it", () => {
  assert.match(orbClasses, /hot/);
});

// Chrome's fake device emits a continuous tone, so the level meter rising is
// proof that frames are being captured, converted and sent.
const ring = await until(
  () => evaluate(`
    const r = document.querySelector('.orb-ring');
    if (!r) return null;
    const m = /scale\\(([0-9.]+)\\)/.exec(r.style.transform || '');
    return m && parseFloat(m[1]) > 1.01 ? parseFloat(m[1]) : null;
  `),
  { what: "mic level to register", timeout: 12000 }
);
check("captured audio is flowing (level meter is live)", () => {
  assert.ok(ring > 1.01, `ring scale was ${ring}`);
});

// --- screenshot --------------------------------------------------------

const shot = await send("Page.captureScreenshot", { format: "png" });
const shotPath = process.env.NITYAM_SHOT ?? resolve(tmpdir(), "nityam-adk-ui.png");
writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
console.log(`\n  screenshot: ${shotPath}`);

check("the page threw no uncaught errors", () => {
  assert.deepEqual(consoleErrors, []);
});

console.log(`\n${passed} passed`);
process.exit(0);
