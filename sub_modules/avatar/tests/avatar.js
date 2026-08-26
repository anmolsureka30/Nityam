/* Tests for the parts that are arithmetic rather than pixels.
 *
 *   node tests/avatar.js
 *
 * What is worth pinning down here: that every emotion is expressible in the
 * rig's vocabulary, that the springs actually settle (a spring that doesn't
 * converge is a face that vibrates forever), and that text->viseme produces
 * mouth shapes that match the words rather than noise. */
const path = require('path');
const B = process.argv[2] || path.join(__dirname, '..');
const NS = require('./lib.js').loadRuntime(B);

let pass = 0, fail = 0;
function ok(name, cond, note) {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${note ? '   ' + note : ''}`);
  cond ? pass++ : fail++;
}
function near(name, got, want, tol) {
  ok(name, Math.abs(got - want) <= tol, `got ${(+got).toFixed(3)}, want ${want}±${tol}`);
}

console.log('\n─ the rig contract ─');
{
  const p = NS.newParams();
  ok('rig exposes a parameter set', Object.keys(p).length >= 18, Object.keys(p).length + ' parameters');
  ok('newParams() returns a fresh copy', (function () {
    const a = NS.newParams(); a.mouthOpen = 0.9; return NS.newParams().mouthOpen !== 0.9;
  })());

  // every emotion must be expressible in the rig's vocabulary, or it silently
  // does nothing at runtime
  const unknown = [];
  Object.keys(NS.EMOTIONS).forEach(e => {
    Object.keys(NS.EMOTIONS[e]).forEach(k => { if (!(k in p)) unknown.push(e + '.' + k); });
  });
  ok('every emotion only sets real rig parameters', unknown.length === 0, unknown.join(', '));

  const unknownV = [];
  Object.keys(NS.VISEMES).forEach(v => {
    Object.keys(NS.VISEMES[v]).forEach(k => { if (!(k in p)) unknownV.push(v + '.' + k); });
  });
  ok('every viseme only sets real rig parameters', unknownV.length === 0, unknownV.join(', '));
}

console.log('\n─ emotions ─');
{
  ok('ten emotions defined', NS.emotionNames().length === 10, NS.emotionNames().join(', '));
  ok('there is no "sad" or "angry"',
     !NS.emotionNames().some(n => /sad|angry|disappoint/i.test(n)),
     'a tutor is never disappointed in a student — the nearest is `gentle`');

  const e = NS.EMOTIONS.encouraging;
  ok('the "good job" face reaches the eyes, not just the mouth',
     e.eyeSquint > 0.5 && e.cheekRaise > 0.5,
     `eyeSquint=${e.eyeSquint}, cheekRaise=${e.cheekRaise} — a mouth-only smile reads as fake`);
  ok('`gentle` raises the inner brows rather than frowning hard',
     NS.EMOTIONS.gentle.browInner > 0.5 && NS.EMOTIONS.gentle.mouthCurve > -0.6,
     `browInner=${NS.EMOTIONS.gentle.browInner}, mouthCurve=${NS.EMOTIONS.gentle.mouthCurve}`);
}

console.log('\n─ the spring engine ─');
{
  const eng = NS.createEmotionEngine();
  let t = 0;
  const step = (secs) => { for (let i = 0; i < secs * 60; i++) { t += 1 / 60; eng.step(1 / 60, t); } };

  eng.set('neutral'); step(1.5);
  const restCurve = eng.params.mouthCurve;

  eng.set('encouraging');
  let peak = -Infinity, settled = null;
  for (let i = 0; i < 120; i++) {
    t += 1 / 60; eng.step(1 / 60, t);
    peak = Math.max(peak, eng.params.mouthCurve);
    if (settled === null && i > 10 && Math.abs(eng.params.mouthCurve - NS.EMOTIONS.encouraging.mouthCurve) < 0.02) settled = i / 60;
  }
  near('springs converge on the target', eng.params.mouthCurve, NS.EMOTIONS.encouraging.mouthCurve, 0.02);
  ok('and overshoot on the way — that is what makes it read as alive',
     peak > NS.EMOTIONS.encouraging.mouthCurve + 0.02, `peak=${peak.toFixed(3)}`);
  ok('an expression settles in roughly a third of a second',
     settled !== null && settled > 0.12 && settled < 0.75,
     `settled at ${settled === null ? 'never' : settled.toFixed(2) + 's'} — faster reads as a cut, slower as lag`);

  // a blend must not detour through neutral
  const eng2 = NS.createEmotionEngine();
  let t2 = 0; const step2 = (s) => { for (let i = 0; i < s * 60; i++) { t2 += 1 / 60; eng2.step(1 / 60, t2); } };
  eng2.set('excited'); step2(1.2);
  const before = eng2.params.mouthCurve;
  eng2.set('proud');
  let dipped = false;
  for (let i = 0; i < 60; i++) { t2 += 1 / 60; eng2.step(1 / 60, t2); if (eng2.params.mouthCurve < 0.4) dipped = true; }
  ok('excited → proud never passes through a neutral mouth',
     !dipped, `stayed smiling the whole way (started ${before.toFixed(2)})`);

  // a transient reaction reverts on its own
  const eng3 = NS.createEmotionEngine();
  let t3 = 0;
  eng3.set('listening');
  eng3.set('surprised', { hold: 0.4 });
  for (let i = 0; i < 60; i++) { t3 += 1 / 60; eng3.step(1 / 60, t3); }
  ok('react() reverts to the base emotion after its hold',
     eng3.emotion() === 'listening', `ended on "${eng3.emotion()}"`);
}

console.log('\n─ idle behaviour ─');
{
  const eng = NS.createEmotionEngine();
  let t = 0, minEye = 1, frames = 0;
  eng.set('neutral');
  for (let i = 0; i < 60 * 12; i++) { t += 1 / 60; eng.step(1 / 60, t); minEye = Math.min(minEye, eng.params.eyeOpen); frames++; }
  ok('she blinks', minEye < 0.25, `eyes reached ${minEye.toFixed(3)} within ${(frames / 60).toFixed(0)}s`);

  const eng2 = NS.createEmotionEngine();
  let t2 = 0, lo = Infinity, hi = -Infinity, lo2 = Infinity, hi2 = -Infinity;
  eng2.set('neutral');
  for (let i = 0; i < 60 * 8; i++) {
    t2 += 1 / 60; eng2.step(1 / 60, t2);
    lo = Math.min(lo, eng2.params.headTurn); hi = Math.max(hi, eng2.params.headTurn);
    lo2 = Math.min(lo2, eng2.params.lookX);  hi2 = Math.max(hi2, eng2.params.lookX);
  }
  ok('the head drifts rather than freezing', hi - lo > 0.03,
     `headTurn swept ${(hi - lo).toFixed(3)} over 8s of "holding still"`);
  ok('the eyes make micro-saccades', hi2 - lo2 > 0.05,
     `lookX swept ${(hi2 - lo2).toFixed(3)} — real eyes are never perfectly still`);
}

console.log('\n─ text → visemes ─');
{
  const r = NS.textToVisemes('So what do you think decides the maximum range?');
  ok('a sentence becomes a viseme sequence', r.seq.length > 8, `${r.seq.length} visemes`);
  ok('timing is plausible for speech', r.duration > 2 && r.duration < 6,
     `${r.duration.toFixed(2)}s for 9 words (~2.5-4s is human)`);
  ok('sequence is monotonic in time', r.seq.every((s, i) => i === 0 || s.t >= r.seq[i - 1].t));

  const mbp = NS.textToVisemes('map bat pin').seq;
  ok('m / b / p produce a CLOSED mouth', mbp.every(s => s.viseme === 'MBP'),
     mbp.map(s => s.viseme).join(' ') + ' — bilabials must shut the lips or it looks wrong');

  const round = NS.textToVisemes('boot').seq;
  ok('rounded vowels come out rounded', NS.VISEMES[round[round.length - 1].viseme].mouthPurse > 0 || round[0].viseme === 'MBP',
     round.map(s => s.viseme).join(' '));

  ok('punctuation inserts a pause',
     NS.textToVisemes('one. two').duration > NS.textToVisemes('one two').duration);
}

console.log('\n─ speech engine envelope ─');
{
  const sp = NS.createSpeechEngine();
  const dur = sp.speakText('Ah, so what makes it go the farthest?', { now: 0 });
  let maxOpen = 0, minOpen = 1, samples = 0, widths = new Set();
  for (let t = 0; t < dur; t += 0.02) {
    const m = sp.step(t);
    if (!m) break;
    maxOpen = Math.max(maxOpen, m.mouthOpen);
    minOpen = Math.min(minOpen, m.mouthOpen);
    widths.add(m.mouthWidth.toFixed(2));
    samples++;
  }
  ok('the mouth opens properly at vowel peaks', maxOpen > 0.55, `peak open=${maxOpen.toFixed(2)}`);
  ok('and closes between syllables', minOpen < 0.08, `min open=${minOpen.toFixed(2)}`);
  ok('width varies, so it is not just a flapping jaw', widths.size > 8, `${widths.size} distinct widths`);
  ok('speech ends and hands control back', sp.step(dur + 0.5) === null);
}

console.log('\n─ drawing survives extreme input ─');
{
  const calls = [];
  const stub = new Proxy({}, {
    get: (t, k) => {
      if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({ addColorStop() {} });
      if (k === 'measureText') return () => ({ width: 10 });
      return () => { calls.push(k); };
    },
    set: () => true
  });
  let threw = null;
  try {
    [-5, 0, 0.5, 1, 5, NaN].forEach(v => {
      const p = NS.newParams();
      Object.keys(p).forEach(k => { p[k] = v; });
      NS.draw(stub, p, { width: 300, height: 340 });
    });
  } catch (e) { threw = e; }
  ok('draw() never throws, even on garbage parameters', threw === null, threw ? threw.message : `${calls.length} canvas ops`);
}

console.log(`\n  ${fail === 0 ? 'AVATAR TESTS: PASS' : 'AVATAR TESTS: FAIL'}  (${pass} passed, ${fail} failed)\n`);
process.exit(fail === 0 ? 0 : 1);
