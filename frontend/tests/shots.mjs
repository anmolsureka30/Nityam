/* Screenshot every screen, so a design change can be looked at rather than
 * imagined. Same bootstrap as tests/ui.mjs: backend in mock mode, the Vite dev
 * server in front of it, headless Chrome over CDP.
 *
 *     NITYAM_SHOTS=/tmp/shots node tests/shots.mjs
 *     NITYAM_SHOTS=/tmp/shots WIDE=390 node tests/shots.mjs   # phone width
 */
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = resolve(ROOT, "..", "backend");
const OUT = process.env.NITYAM_SHOTS ?? resolve(tmpdir(), "nityam-shots");
const W = Number(process.env.WIDE ?? 1440);
const H = Number(process.env.TALL ?? 1000);
mkdirSync(OUT, { recursive: true });

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
const profile = mkdtempSync(resolve(tmpdir(), "nity-s-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME,
  ["--headless=new", `--remote-debugging-port=${CDP}`, `--user-data-dir=${profile}`,
   "--no-first-run", "--disable-gpu", "--hide-scrollbars",
   /* A microphone, granted without a prompt. Without these the page
      gets NotAllowedError, SpeechBubble shows "I lost the connection —
      microphone: Permission denied", and every assertion about her
      captions was silently measuring that error string instead of
      anything she said. */
   "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
   `--window-size=${W},${H}`, "--force-device-scale-factor=2", "about:blank"],
  { stdio: "ignore" });

const reap = () => { chrome.kill("SIGKILL"); web.kill("SIGKILL"); srv.kill("SIGKILL"); };
process.on("exit", reap);
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => { reap(); process.exit(130); });
}
process.on("uncaughtException", (e) => { reap(); throw e; });

for (let i = 0; i < 400; i++) {
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
  new Promise((res, rej) => {
    const i = id++;
    pend.set(i, { resolve: res, reject: rej });
    ws.send(JSON.stringify({ id: i, method: m, params: p }));
  });
const ev = async (e) => {
  const r = await send("Runtime.evaluate", {
    expression: `(async()=>{${e}})()`, awaitPromise: true, returnByValue: true,
  });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description);
  return r.result.value;
};
await send("Page.enable");
await send("Runtime.enable");

const shot = async (name, { full = false } = {}) => {
  const r = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: full,
    ...(full
      ? {}
      : {}),
  });
  const file = resolve(OUT, `${name}.png`);
  writeFileSync(file, Buffer.from(r.data, "base64"));
  console.log(`  ${name}.png`);
};

const go = async (path, wait = 1400) => {
  await send("Page.navigate", { url: `http://localhost:${APP}${path}` });
  await sleep(wait);
};

console.log(`\nshooting ${W}x${H} into ${OUT}\n`);

await go("/");
await shot("01-home");

// Straight to a session, then let the mock tutor write a few blocks so the
// notebook is shown with real content rather than empty.
await go("/session", 2600);
await shot("02-session-empty");

await ev(`
  const i = document.querySelector('input[aria-label="Ask Nityam"]');
  if (i) { i.focus(); }
  return 1;
`);
await send("Input.insertText", { text: "why is 45 degrees the best angle?" });
await send("Input.dispatchKeyEvent", {
  type: "keyDown", key: "Enter", code: "Enter", text: "\r",
  windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
});
await send("Input.dispatchKeyEvent", {
  type: "keyUp", key: "Enter", code: "Enter",
  windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
});
/* Wait for the POINTER rather than guessing at a delay. The stick is only up
   while she is speaking AND an anchor is hot, and every fixed sleep I tried
   landed either before she started or after she stopped. */
for (let i = 0; i < 60; i++) {
  const up = await ev(`return !!document.querySelector('svg[class*="layer"] path');`);
  if (up) break;
  await sleep(250);
}
await shot("03-session-written");
await sleep(3200);
await shot("03b-session-settled");

await ev(`
  const b = [...document.querySelectorAll('button')].find(b=>/View textbook/.test(b.textContent));
  b?.click(); return 1;
`);
await sleep(3200);
await shot("04-textbook");
await ev(`
  const c = [...document.querySelectorAll('[role=dialog] button')].find(b=>/Close|✕/.test(b.textContent));
  c?.click(); return 1;
`);
await sleep(700);

for (const [path, name] of [
  ["/readiness", "05-readiness"],
  ["/intensity/PHY-11-K2", "06-intensity"],
  ["/summary", "07-summary"],
  ["/teacher", "08-teacher"],
  ["/teacher/insights", "09-teacher-insights"],
  ["/teacher/intervene", "10-teacher-intervene"],
]) {
  await go(path);
  await shot(name);
}

console.log("\ndone\n");
process.exit(0);
