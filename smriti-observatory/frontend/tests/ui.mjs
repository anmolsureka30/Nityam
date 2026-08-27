/* Drives the built Observatory frontend in headless Chrome over the
 * DevTools protocol — same approach as frontend/tests/ui.mjs (the product
 * app's own harness). No Puppeteer, no test runner.
 *
 *   npm run build && node tests/ui.mjs
 */
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const freePort = () =>
  new Promise((r) => {
    const s = createServer();
    s.unref();
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => r(port));
    });
  });

const APP = await freePort();
const CDP = await freePort();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const srv = spawn("npx", ["vite", "preview", "--port", String(APP), "--strictPort", "--host", "127.0.0.1"], {
  cwd: ROOT,
  stdio: "ignore",
});
const profile = mkdtempSync(resolve(tmpdir(), "smriti-obs-v-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${CDP}`,
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--disable-gpu",
    "--hide-scrollbars",
    "--window-size=1440,1000",
    "about:blank",
  ],
  { stdio: "ignore" },
);
process.on("exit", () => {
  chrome.kill("SIGKILL");
  srv.kill("SIGKILL");
});

for (let i = 0; i < 200; i++) {
  try {
    if ((await fetch(`http://127.0.0.1:${APP}/`)).ok) break;
  } catch {}
  await sleep(120);
}

let url;
for (let i = 0; i < 90; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();
    const page = list.find((t) => t.type === "page");
    if (page?.webSocketDebuggerUrl) {
      url = page.webSocketDebuggerUrl;
      break;
    }
  } catch {}
  await sleep(150);
}

let id = 1;
const pending = new Map();
const ws = new WebSocket(url);
await new Promise((resolvePromise, reject) => {
  ws.onopen = resolvePromise;
  ws.onerror = reject;
});
ws.onmessage = ({ data }) => {
  const parsed = JSON.parse(data);
  const waiter = pending.get(parsed.id);
  if (waiter) {
    pending.delete(parsed.id);
    parsed.error ? waiter.reject(new Error(parsed.error.message)) : waiter.resolve(parsed.result);
  }
};
const send = (method, params = {}) =>
  new Promise((resolvePromise, reject) => {
    const thisId = id++;
    pending.set(thisId, { resolve: resolvePromise, reject });
    ws.send(JSON.stringify({ id: thisId, method, params }));
  });
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression: `(()=>{${expression}})()`, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
  return result.result.value;
};

await send("Page.enable");
await send("Runtime.enable");
const errors = [];
ws.addEventListener("message", ({ data }) => {
  const parsed = JSON.parse(data);
  if (parsed.method === "Runtime.exceptionThrown") errors.push(parsed.params.exceptionDetails.text);
});

await send("Page.navigate", { url: `http://127.0.0.1:${APP}/` });
await sleep(1500);

const hasDrawer = await evaluate(`return document.querySelector('nav[aria-label="Sessions"]') !== null;`);
if (!hasDrawer) throw new Error("SessionDrawer did not render");

const bodyBackground = await evaluate(`return getComputedStyle(document.body).backgroundColor;`);
if (bodyBackground !== "rgb(18, 18, 18)") {
  throw new Error(`expected ADK-web dark background rgb(18, 18, 18), got ${bodyBackground}`);
}

if (errors.length > 0) {
  throw new Error(`console errors during load: ${errors.join("; ")}`);
}

console.log("ui.mjs: PASS — SessionDrawer renders, dark theme tokens applied, no console errors");
