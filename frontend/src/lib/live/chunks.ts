/* Breaking what she says into the pieces a speech bubble can hold.
 *
 * A bubble showing a whole paragraph is a transcript, not speech. She routinely
 * returns three sentences in one settled transcription:
 *
 *   "Maine board par height aur range dono ke formulas note kar diye hain.
 *    Maximum height vertical velocity decide karti hai, lekin range ke liye
 *    angle sabse crucial factor hai. Agar fixed speed se ball hit karein, toh
 *    maximum range pane ke liye angle kya hona chahiye?"
 *
 * so the whole thing arrived at once and sat there as a wall of text.
 *
 * Splitting on sentences alone is not enough — the middle sentence above is 14
 * words and still too long for one glance — so a long sentence is broken again
 * at a clause boundary. Breaking at commas FIRST would be wrong: it shatters
 * short sentences that were fine as they were.
 */

/** Comfortable for one glance. Above this a chunk gets split at a clause. */
const MAX_WORDS = 11;

/** Below this, a trailing fragment is glued back onto the previous chunk rather
 *  than flashed up on its own — "toh maximum range pane ke liye" followed by a
 *  two-word chunk reads as a stutter. */
const MIN_WORDS = 3;

const words = (text: string) => text.trim().split(/\s+/).filter(Boolean);

/** Sentence ends: . ? ! and the Devanagari danda, which she uses when speaking
 *  Hindi. Keeps the punctuation with the sentence it closes. */
function sentences(text: string): string[] {
  return text
    .split(/(?<=[.!?।])\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Split one over-long sentence at its latest clause boundary before the limit,
 *  so the break lands where a speaker would breathe. */
function atClause(sentence: string): string[] {
  const parts = words(sentence);
  if (parts.length <= MAX_WORDS) return [sentence];

  // Candidate break points: after a comma, dash, semicolon or colon.
  const breaks: number[] = [];
  parts.forEach((word, i) => {
    if (/[,;:—–]$/.test(word) && i > 0) breaks.push(i + 1);
  });

  const target = Math.min(MAX_WORDS, Math.ceil(parts.length / 2));
  // The last break at or before the target, else the first break after it,
  // else a hard split at the target.
  const before = breaks.filter((b) => b <= MAX_WORDS);
  const cut = before.length
    ? before[before.length - 1]
    : breaks.find((b) => b < parts.length) ?? target;

  const head = parts.slice(0, cut).join(" ");
  const tail = parts.slice(cut).join(" ");
  return [head, ...atClause(tail)];
}

/** What she said, as bubble-sized pieces. */
export function toChunks(text: string): string[] {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return [];

  const out: string[] = [];
  for (const sentence of sentences(clean)) {
    for (const piece of atClause(sentence)) {
      const n = words(piece).length;
      // Glue a runt onto its predecessor rather than showing it alone.
      if (n < MIN_WORDS && out.length) out[out.length - 1] += ` ${piece}`;
      else out.push(piece);
    }
  }
  return out;
}

/** Roughly how long she will take to say this, in milliseconds.
 *
 *  ~2.6 words/second is measured conversational speech. This only has to be
 *  close: the chunk clock is gated on her actually making sound, so every pause
 *  re-synchronises it and the estimate cannot drift far.
 */
export function spokenMs(chunk: string): number {
  const n = words(chunk).length;
  return Math.max(900, Math.round((n / 2.6) * 1000));
}
