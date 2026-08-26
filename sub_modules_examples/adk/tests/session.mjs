// End-to-end test of the real WebSocket protocol, in mock mode.
//
// Spawns uvicorn, drives the socket exactly as the browser does — binary PCM
// frames up, ADK-shaped event JSON down — and asserts on the event stream.
// No API key, no browser, no credits.
//
//   node tests/session.mjs
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;


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

// ------------------------------------------------------------- helpers

function pcm16(seconds, amplitude, rate = 16000) {
  const n = Math.floor(rate * seconds);
  const buf = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) {
    const v = Math.sin((2 * Math.PI * 190 * i) / rate) * amplitude;
    buf.writeInt16LE(Math.round(v * 32767), i * 2);
  }
  return buf;
}

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


async function waitFor(predicate, { timeout = 15000, what = "condition" } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
    await sleep(40);
  }
  throw new Error(`timed out waiting for ${what}`);
}

// ------------------------------------------------------------- server

const server = spawn(
  resolve(ROOT, ".venv/bin/uvicorn"),
  ["--app-dir", "backend", "main:app", "--port", String(PORT), "--log-level", "warning"],
  { cwd: ROOT, env: { ...process.env, NITYAM_AUTH: "mock" }, stdio: ["ignore", "pipe", "pipe"] }
);
let serverLog = "";
server.stdout.on("data", (d) => (serverLog += d));
server.stderr.on("data", (d) => (serverLog += d));

const stop = reap(server);

async function waitForHealth(timeout = 25000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE}/health`);
      if (response.ok) return await response.json();
    } catch {
      // not listening yet
    }
    await sleep(120);
  }
  throw new Error("server did not start");
}

let health;
try {
  health = await waitForHealth();
} catch (err) {
  console.error(serverLog);
  throw err;
}
check("server reports mock mode on /health", () => {
  assert.equal(health.status, "ok");
  assert.equal(health.mode, "mock");
});

// ------------------------------------------------------------- socket

const events = [];
const control = [];
const audioChunks = [];

const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws/test-user/test-session`);
ws.binaryType = "arraybuffer";
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = () => rej(new Error("socket failed to open"));
});

ws.onmessage = (message) => {
  const payload = JSON.parse(message.data);
  if (payload.nityam) {
    control.push(payload.nityam);
    return;
  }
  events.push(payload);
  for (const part of payload.content?.parts ?? []) {
    if (part.inlineData?.mimeType?.startsWith("audio/pcm")) {
      audioChunks.push(part.inlineData);
    }
  }
};

await waitFor(() => control.length > 0, { what: "session control message" });
check("server announces the session up front", () => {
  assert.equal(control[0].kind, "session");
  assert.equal(control[0].mode, "mock");
});

// --- greeting -----------------------------------------------------------

ws.send(JSON.stringify({ type: "greet" }));
await waitFor(() => events.some((e) => e.turnComplete), { what: "greeting turn" });

check("greeting streams audio at the Live API output rate", () => {
  assert.ok(audioChunks.length > 5, `only ${audioChunks.length} audio chunks`);
  assert.equal(audioChunks[0].mimeType, "audio/pcm;rate=24000");
  const bytes = Buffer.from(audioChunks[0].data, "base64");
  assert.ok(bytes.length > 0);
  assert.equal(bytes.length % 2, 0, "PCM16 frames must be an even byte count");
});

check("greeting produces a readable transcript", () => {
  const text = events
    .filter((e) => e.outputTranscription)
    .map((e) => e.outputTranscription.text)
    .join("");
  assert.match(text, /Nityam/);
});

check("transcription arrives as partials then one consolidated sentence", () => {
  // This is the real Live API's shape, and the reason it matters: the
  // consolidated event repeats the entire sentence, so a client that appends
  // every fragment prints the greeting twice.
  const partials = events.filter((e) => e.outputTranscription && e.partial);
  const settled = events.filter((e) => e.outputTranscription && e.partial === false);
  assert.ok(partials.length > 0, "no partial transcription events");
  assert.ok(settled.length > 0, "no consolidated transcription event");

  const rebuilt = partials.map((e) => e.outputTranscription.text).join("").trim();
  const consolidated = settled.map((e) => e.outputTranscription.text).join(" ").trim();
  assert.equal(consolidated.replace(/\s+/g, " "), rebuilt.replace(/\s+/g, " "));
  assert.ok(settled.every((e) => e.outputTranscription.finished === true));
});

check("every event names its author", () => {
  assert.ok(events.every((e) => typeof e.author === "string" && e.author));
});

// --- agent transfer -----------------------------------------------------

const before = events.length;
ws.send(JSON.stringify({ type: "text", text: "quiz me please" }));
await waitFor(
  () => events.slice(before).some((e) => e.turnComplete),
  { what: "quiz turn" }
);
const quizTurn = events.slice(before);

check("asking for a quiz transfers to the second agent", () => {
  const transfer = quizTurn.find((e) =>
    (e.content?.parts ?? []).some((p) => p.functionCall?.name === "transfer_to_agent")
  );
  assert.ok(transfer, "no transfer_to_agent call");
  const target = transfer.content.parts.find((p) => p.functionCall).functionCall.args
    .agent_name;
  assert.equal(target, "quiz_master");
});

check("the second agent is the one that then speaks", () => {
  const speakers = new Set(
    quizTurn.filter((e) => e.outputTranscription).map((e) => e.author)
  );
  assert.ok(speakers.has("quiz_master"), `speakers were ${[...speakers]}`);
});

check("the quiz agent reports score through its tool", () => {
  const tool = quizTurn
    .flatMap((e) => e.content?.parts ?? [])
    .find((p) => p.functionResponse?.name === "record_answer");
  assert.ok(tool, "no record_answer response");
  assert.equal(tool.functionResponse.response.asked, 1);
});

// --- microphone path and interruption -----------------------------------

const mark = events.length;
// A second of speech-level audio, then silence: the mock VAD should call the
// turn over and answer, exactly as server-side VAD does for the real API.
for (const chunk of chunks(pcm16(1.0, 0.5), 3200)) {
  ws.send(chunk);
  await sleep(12);
}
for (const chunk of chunks(pcm16(0.9, 0.0), 3200)) {
  ws.send(chunk);
  await sleep(12);
}

await waitFor(
  () => events.slice(mark).some((e) => e.outputTranscription),
  { what: "reply to spoken input", timeout: 20000 }
);
check("streaming mic audio triggers a spoken reply", () => {
  const replied = events.slice(mark).filter((e) => e.outputTranscription);
  assert.ok(replied.length > 0);
});

const speakingMark = events.length;
// Talk over it. The real API raises interrupted; the mock mirrors that so the
// client's buffer-flush path is exercised.
for (const chunk of chunks(pcm16(0.5, 0.6), 3200)) {
  ws.send(chunk);
  await sleep(10);
}
const interrupted = await waitFor(
  () => events.slice(speakingMark).find((e) => e.interrupted),
  { what: "interruption event" }
).catch(() => null);

check("talking over the model interrupts it", () => {
  assert.ok(interrupted, "no interrupted event was emitted");
});

ws.close();
stop();

console.log(`\n${passed} passed`);
// The spawned server and the socket both keep the loop alive; nothing is
// pending, so leave deliberately rather than hanging on an idle handle.
process.exit(0);

function* chunks(buffer, size) {
  for (let i = 0; i < buffer.length; i += size) yield buffer.subarray(i, i + size);
}
