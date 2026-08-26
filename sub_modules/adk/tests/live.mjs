// The one test that costs money: the real server against the real Live API.
//
// Everything else runs against the mock. This proves the seam between them by
// driving the identical WebSocket protocol and asserting that real audio and
// real transcription come back, attributed to a real agent.
//
//   node tests/live.mjs          (uses .env; needs a working NITYAM_AUTH)
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
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

const server = spawn(
  resolve(ROOT, ".venv/bin/uvicorn"),
  ["--app-dir", "backend", "main:app", "--port", String(PORT), "--log-level", "warning"],
  { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] }
);
let log = "";
server.stdout.on("data", (d) => (log += d));
server.stderr.on("data", (d) => (log += d));
reap(server);

let health;
for (let i = 0; i < 200; i++) {
  try {
    const response = await fetch(`${BASE}/health`);
    if (response.ok) { health = await response.json(); break; }
  } catch { /* not up */ }
  await sleep(120);
}
if (!health) { console.error(log); throw new Error("server did not start"); }

if (health.mode === "mock") {
  console.log(`  SKIP: .env has NITYAM_AUTH=mock — nothing live to test.`);
  process.exit(0);
}
console.log(`  backend: ${health.detail}\n`);

const events = [];
let audioBytes = 0;
let controlError = null;

const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws/live-test/live-${Date.now()}`);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
ws.onmessage = ({ data }) => {
  const payload = JSON.parse(data);
  if (payload.nityam) {
    if (payload.nityam.kind === "error") controlError = payload.nityam.message;
    return;
  }
  events.push(payload);
  for (const part of payload.content?.parts ?? []) {
    if (part.inlineData?.mimeType?.startsWith("audio/pcm")) {
      audioBytes += Buffer.from(part.inlineData.data, "base64").length;
    }
  }
};

// First prove the tutor opens the conversation by itself, the way the UI
// expects when a student connects.
ws.send(JSON.stringify({ type: "greet" }));
const greetDeadline = Date.now() + 60_000;
while (Date.now() < greetDeadline && !controlError) {
  if (events.some((e) => e.turnComplete) && audioBytes > 0) break;
  await sleep(250);
}
const greetedWith = events
  .filter((e) => e.outputTranscription && e.partial === false)
  .map((e) => e.outputTranscription.text)
  .join(" ")
  .trim();
const greetAudio = audioBytes;

// Everything from here belongs to the SECOND turn. Without this mark the wait
// below would see the greeting's own turnComplete and return immediately.
const mark = events.length;
ws.send(JSON.stringify({
  type: "text",
  text: "In one short sentence, what is the formula for the range of a projectile?",
}));

// Real generation takes seconds; wait for the turn rather than a fixed sleep.
const deadline = Date.now() + 90_000;
while (Date.now() < deadline) {
  if (controlError) break;
  const turn = events.slice(mark);
  if (turn.some((e) => e.turnComplete) && audioBytes > greetAudio) break;
  await sleep(250);
}
const answerTurn = events.slice(mark);

if (controlError) {
  console.error(`\n  server reported: ${controlError}\n`);
  if (/UNAUTHENTICATED|401/.test(controlError)) {
    console.error("  The OAuth access token has expired (they last ~1 hour).");
    console.error("  Mint a fresh GOOGLE_OAUTH_ACCESS_TOKEN in .env and retry.");
  }
  process.exit(1);
}

check("the tutor opens the conversation unprompted", () => {
  assert.ok(greetAudio > 10000, `greeting produced only ${greetAudio} audio bytes`);
  assert.ok(greetedWith.length > 5, `greeting transcript was ${JSON.stringify(greetedWith)}`);
  // The stage direction that triggered it must never surface to the student.
  assert.ok(
    !/student has just joined|do not mention/i.test(greetedWith),
    `the greeting cue leaked into speech: ${greetedWith}`
  );
});

check("answering a question returns its own audio", () => {
  const spoken = audioBytes - greetAudio;
  assert.ok(spoken > 10000, `only ${spoken} bytes of audio for the answer`);
});

check("audio is PCM16, and any declared rate matches the player", () => {
  // Vertex sends a bare `audio/pcm` and leaves the rate implicit; AI Studio
  // spells out `;rate=24000`. Accept both, but if a rate IS declared it had
  // better be the one the playback worklet was built for.
  const first = answerTurn
    .flatMap((e) => e.content?.parts ?? [])
    .find((p) => p.inlineData?.mimeType?.startsWith("audio/pcm"));
  assert.ok(first, "no PCM audio part at all");
  const declared = /rate=(\d+)/.exec(first.inlineData.mimeType);
  if (declared) assert.equal(declared[1], "24000");
  else console.log(`      (rate not declared: ${first.inlineData.mimeType})`);
});

const transcript = answerTurn
  .filter((e) => e.outputTranscription && e.partial === false)
  .map((e) => e.outputTranscription.text)
  .join(" ");

check("the model's speech was transcribed", () => {
  assert.ok(transcript.length > 10, `transcript was ${JSON.stringify(transcript)}`);
});

check("transcription really does arrive as partials plus a consolidation", () => {
  // The assumption the whole caption pipeline rests on, verified against the
  // real API rather than against the mock that imitates it.
  assert.ok(answerTurn.some((e) => e.outputTranscription && e.partial === true));
  assert.ok(answerTurn.some((e) => e.outputTranscription && e.partial === false));
});

check("events are attributed to a named agent", () => {
  const authors = new Set(events.map((e) => e.author).filter(Boolean));
  assert.ok(authors.has("tutor") || authors.has("quiz_master"), [...authors].join());
});

// --- tool calling, on the pattern that failed in a real session ------------
//
// The tutor used to answer "here it is" without ever calling show_formula, so
// the student's screen stayed empty while she claimed otherwise. The request is
// deliberately vague Hinglish, which is how it failed.
const toolMark = events.length;
ws.send(JSON.stringify({ type: "text", text: "mujhe range formula dikha doge aap?" }));
const toolDeadline = Date.now() + 60_000;
while (Date.now() < toolDeadline && !controlError) {
  const turn = events.slice(toolMark);
  if (turn.some((e) => e.turnComplete) && turn.some((e) => e.outputTranscription)) break;
  await sleep(250);
}
const toolTurn = events.slice(toolMark);
const toolParts = toolTurn.flatMap((e) => e.content?.parts ?? []);
const toolSaid = toolTurn
  .filter((e) => e.outputTranscription && e.partial === false)
  .map((e) => e.outputTranscription.text)
  .join(" ");

check("asking for a formula actually calls show_formula", () => {
  const called = toolParts.some((p) => p.functionCall?.name === "show_formula");
  assert.ok(called, `no show_formula call. She said: ${JSON.stringify(toolSaid)}`);
});

check("ADK executed the tool and fed the result back", () => {
  const response = toolParts.find((p) => p.functionResponse?.name === "show_formula");
  assert.ok(response, "tool was called but never executed");
  assert.match(response.functionResponse.response.formula ?? "", /R\s*=/);
});

check("she never claims to have shown something she did not", () => {
  const claimed = /(here it is|dikha (diya|deta|raha)|दिखा (दिया|रहा)|on your screen)/i;
  const called = toolParts.some((p) => p.functionCall?.name === "show_formula");
  if (claimed.test(toolSaid)) {
    assert.ok(called, `claimed to have shown it without calling the tool: ${toolSaid}`);
  }
});

const tools = toolTurn
  .flatMap((e) => e.content?.parts ?? [])
  .map((p) => p.functionCall?.name ?? p.functionResponse?.name)
  .filter(Boolean);
console.log(`\n  greeting: ${JSON.stringify(greetedWith.slice(0, 120))}`);
console.log(`  audio: ${audioBytes} bytes total | tools: ${tools.join(", ") || "none"}`);
console.log(`  said: ${JSON.stringify(transcript.slice(0, 160))}`);
console.log(`  formula turn: ${JSON.stringify(toolSaid.slice(0, 120))}`);

console.log(`\n${passed} passed`);
process.exit(0);
