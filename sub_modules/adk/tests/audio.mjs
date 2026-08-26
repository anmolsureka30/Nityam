// Unit tests for the pure audio helpers. No browser, no server, no API key.
//   node tests/audio.test.js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// atob exists in node 16+, but the module is written for a browser; make the
// global explicit so the import works unchanged.
globalThis.atob ??= (s) => Buffer.from(s, "base64").toString("binary");

const { floatToPCM16, base64ToArrayBuffer, rms } = await import("../frontend/src/audio.js");

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log(`  ok  ${name}`);
}

check("full scale maps to int16 extremes", () => {
  const out = floatToPCM16(new Float32Array([0, 1, -1]));
  assert.equal(out[0], 0);
  assert.equal(out[1], 32767);
  assert.equal(out[2], -32767);
});

check("out-of-range input clamps instead of wrapping", () => {
  // The bug this guards: 1.5 * 32767 overflows int16 and wraps to a large
  // negative sample, which is an audible crack.
  const out = floatToPCM16(new Float32Array([1.5, -2.0]));
  assert.equal(out[0], 32767);
  assert.equal(out[1], -32767);
});

check("round trip through int16 preserves the signal within a quantum", () => {
  const input = new Float32Array(256);
  for (let i = 0; i < input.length; i++) input[i] = Math.sin(i / 8) * 0.8;
  const pcm = floatToPCM16(input);
  for (let i = 0; i < input.length; i++) {
    assert.ok(Math.abs(pcm[i] / 32767 - input[i]) < 1 / 32767);
  }
});

check("standard base64 decodes to the right bytes", () => {
  const buf = base64ToArrayBuffer(Buffer.from([1, 2, 3, 250]).toString("base64"));
  assert.deepEqual([...new Uint8Array(buf)], [1, 2, 3, 250]);
});

check("base64url with missing padding still decodes", () => {
  const bytes = Buffer.from([255, 254, 253, 0, 17]);
  const urlish = bytes
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  assert.deepEqual([...new Uint8Array(base64ToArrayBuffer(urlish))], [...bytes]);
});

check("a 100ms chunk of 24kHz PCM16 is 4800 bytes", () => {
  // Sanity check on the rate assumptions the worklets depend on.
  assert.equal(24000 * 0.1 * 2, 4800);
  assert.equal(16000 * 0.1 * 2, 3200);
});

check("rms is zero for silence and near 0.707 for a full sine", () => {
  assert.equal(rms(new Float32Array(64)), 0);
  const sine = new Float32Array(1024);
  for (let i = 0; i < sine.length; i++) sine[i] = Math.sin((2 * Math.PI * i) / 64);
  assert.ok(Math.abs(rms(sine) - Math.SQRT1_2) < 0.01);
});

check("worklets agree on the rates the session declares", () => {
  const player = readFileSync(new URL("../frontend/public/pcm-player-processor.js", import.meta.url), "utf8");
  const session = readFileSync(new URL("../frontend/src/liveSession.js", import.meta.url), "utf8");
  assert.ok(player.includes("24000"), "player buffer sized at 24kHz");
  assert.ok(session.includes("INPUT_RATE = 16000"));
  assert.ok(session.includes("OUTPUT_RATE = 24000"));
});

check("interruption clears the queue rather than draining it", () => {
  const player = readFileSync(new URL("../frontend/public/pcm-player-processor.js", import.meta.url), "utf8");
  assert.ok(player.includes("endOfAudio"));
  assert.ok(/readIndex = this\.writeIndex/.test(player));
});

console.log(`\n${passed} passed`);
