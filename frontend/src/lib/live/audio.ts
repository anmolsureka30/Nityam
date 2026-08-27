/* Pure audio helpers, kept apart from the session so they can be tested in
 * node without a browser. Ported from sub_modules_examples/adk/frontend/src/audio.js. */

/** Web Audio hands us Float32 in [-1, 1]; the Live API wants signed 16-bit.
 *  Clamping matters: a mic peak above 1.0 wraps to a loud negative sample
 *  otherwise, which sounds like a gunshot in the middle of a sentence. */
export function floatToPCM16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const clamped = Math.max(-1, Math.min(1, input[i]));
    out[i] = Math.round(clamped * 32767);
  }
  return out;
}

/** Event JSON carries audio as base64. Google may emit base64url (- and _
 *  instead of + and /) and may omit padding, so normalise both. */
export function base64ToArrayBuffer(base64: string): ArrayBuffer {
  let standard = base64.replace(/-/g, "+").replace(/_/g, "/");
  while (standard.length % 4) standard += "=";
  const binary = atob(standard);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

/** Root-mean-square level of a frame, for the mic meter. */
export function rms(frame: Float32Array): number {
  if (!frame.length) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}
