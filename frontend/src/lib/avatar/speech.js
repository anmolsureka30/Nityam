/* Ported verbatim from sub_modules_examples/avatar/runtime/speech.js.
 *
 * The ONLY edit is the last line: the IIFE is handed a local namespace object
 * instead of window.Nityam. The drawing code is untouched on purpose — the
 * whole point of the rig is that the face is defined there, so any "tidying"
 * here would make the product's tutor stop matching the module's.
 */
import { NS } from "./ns.js";

/* Lip sync.
 *
 * Research finding worth recording: there is no off-the-shelf audio-to-lipsync
 * for Rive, Lottie or Spine characters — whichever renderer you pick, this
 * layer gets built. So it is built here, renderer-agnostic, and it emits
 * VISEMES rather than pixels.
 *
 * Two drivers, same output:
 *
 *   fromAudio(el|stream)  Web Audio AnalyserNode -> FFT band energies ->
 *                         viseme. Real, sub-frame latency, no network.
 *   fromText(string)      a synthetic envelope built from the actual syllables,
 *                         so the demo works with no microphone and no TTS —
 *                         and still moves in a way that matches the words.
 *
 * A viseme is a target for four mouth parameters. Coarticulation (the smooth
 * blur between shapes that makes real speech legible) is handled for free by
 * the emotion engine's springs. */
(function (NS) {

  /* Preston-Blair style set, reduced to what reads at this stylisation. */
  var VISEMES = {
    REST: { mouthOpen: 0.05, mouthWidth: 0.50, mouthPurse: 0.00, teeth: 0.00 },
    MBP:  { mouthOpen: 0.00, mouthWidth: 0.46, mouthPurse: 0.10, teeth: 0.00 },  // m b p — shut
    AA:   { mouthOpen: 0.85, mouthWidth: 0.66, mouthPurse: 0.00, teeth: 0.55 },  // father
    E:    { mouthOpen: 0.42, mouthWidth: 0.86, mouthPurse: 0.00, teeth: 0.70 },  // bed
    I:    { mouthOpen: 0.22, mouthWidth: 0.80, mouthPurse: 0.00, teeth: 0.55 },  // bit
    O:    { mouthOpen: 0.52, mouthWidth: 0.30, mouthPurse: 0.72, teeth: 0.20 },  // go
    U:    { mouthOpen: 0.26, mouthWidth: 0.22, mouthPurse: 0.92, teeth: 0.05 },  // boot
    FV:   { mouthOpen: 0.14, mouthWidth: 0.62, mouthPurse: 0.00, teeth: 0.85 },  // f v
    L:    { mouthOpen: 0.36, mouthWidth: 0.58, mouthPurse: 0.00, teeth: 0.45 },  // l th n
    S:    { mouthOpen: 0.16, mouthWidth: 0.72, mouthPurse: 0.00, teeth: 0.80 }   // s z sh
  };
  NS.VISEMES = VISEMES;

  /* ── text -> viseme sequence ─────────────────────────────────────────
     Not phoneme-accurate, and it doesn't need to be: matching the RHYTHM and
     the rounded/wide distinction is what the eye actually checks.          */
  var VOWEL_MAP = { a: 'AA', e: 'E', i: 'I', o: 'O', u: 'U', y: 'I' };

  function visemeForChunk(chunk) {
    var c = chunk.toLowerCase();
    if (/^[mbp]/.test(c)) return 'MBP';
    if (/^[fv]/.test(c)) return 'FV';
    if (/^(s|z|sh|ch|j)/.test(c)) return 'S';
    if (/^(l|th|n|d|t)/.test(c)) return 'L';
    var m = c.match(/[aeiouy]/);
    return m ? (VOWEL_MAP[m[0]] || 'AA') : 'L';
  }

  /* Split into rough syllables: a run of consonants plus its vowel cluster. */
  function syllables(word) {
    var out = word.toLowerCase().match(/[^aeiouy]*[aeiouy]+(?:[^aeiouy]*(?=[^aeiouy][aeiouy]))?[^aeiouy]*/g);
    return (out && out.length) ? out : [word];
  }

  NS.textToVisemes = function (text, opts) {
    opts = opts || {};
    var rate = opts.syllablesPerSecond || 4.6;
    var seq = [], t = 0;
    text.split(/\s+/).filter(Boolean).forEach(function (word, wi) {
      var clean = word.replace(/[^A-Za-z']/g, '');
      if (!clean) { t += 0.16; return; }                    // punctuation = a beat
      syllables(clean).forEach(function (syl) {
        var dur = (1 / rate) * (0.75 + Math.random() * 0.5);
        seq.push({ t: t, dur: dur, viseme: visemeForChunk(syl), stress: syl.length > 3 ? 1 : 0.8 });
        t += dur;
      });
      if (/[.,;:!?]$/.test(word)) t += 0.22;                // pause at punctuation
      t += 0.045;
    });
    return { seq: seq, duration: t };
  };

  /* ── the driver ──────────────────────────────────────────────────────── */
  NS.createSpeechEngine = function (opts) {
    opts = opts || {};
    var mode = null;            // 'text' | 'audio' | null
    var seq = null, startedAt = 0, duration = 0;
    var analyser = null, freqData = null, audioCtx = null, srcNode = null;
    var level = 0, closed = 1;
    var current = VISEMES.REST;
    var onEnd = null;

    function speakText(text, o) {
      o = o || {};
      var built = NS.textToVisemes(text, o);
      seq = built.seq; duration = built.duration;
      startedAt = o.now != null ? o.now : (performance.now() / 1000);
      mode = 'text';
      onEnd = o.onEnd || null;
      return duration;
    }

    /* Real audio. Works with an <audio> element or a MediaStream. */
    function attachAudio(source) {
      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        if (srcNode) { try { srcNode.disconnect(); } catch (e) {} }
        srcNode = source instanceof MediaStream
          ? audioCtx.createMediaStreamSource(source)
          : audioCtx.createMediaElementSource(source);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.55;
        srcNode.connect(analyser);
        if (!(source instanceof MediaStream)) analyser.connect(audioCtx.destination);
        freqData = new Uint8Array(analyser.frequencyBinCount);
        mode = 'audio';
        return true;
      } catch (e) {
        console.warn('[nityam:avatar] audio lip sync unavailable:', e.message);
        return false;
      }
    }

    /* Energy in a frequency range, as a 0..1 average. */
    function band(lo, hi) {
      var nyq = audioCtx.sampleRate / 2, n = freqData.length;
      var a = Math.max(0, Math.floor(lo / nyq * n));
      var b = Math.min(n - 1, Math.ceil(hi / nyq * n));
      var s = 0;
      for (var i = a; i <= b; i++) s += freqData[i];
      return (s / Math.max(1, b - a + 1)) / 255;
    }

    /* Classify a frame. F1 (roughly 300-900Hz) carries openness; the ratio of
       F2 (900-2600Hz) to F1 separates wide vowels from rounded ones. */
    function analyse() {
      analyser.getByteFrequencyData(freqData);
      var lowF = band(90, 300);
      var f1 = band(300, 900);
      var f2 = band(900, 2600);
      var hiss = band(3500, 8000);

      var energy = Math.max(f1, f2 * 0.8, lowF * 0.6);
      level = level * 0.5 + energy * 0.5;

      if (level < 0.045) return { v: VISEMES.MBP, amp: 0 };
      if (hiss > f1 * 1.25 && hiss > 0.12) return { v: VISEMES.S, amp: level };

      var ratio = f2 / (f1 + f2 + 1e-6);      // high = wide, low = rounded
      var pick;
      if (ratio > 0.60) pick = level > 0.35 ? VISEMES.E : VISEMES.I;
      else if (ratio < 0.36) pick = level > 0.35 ? VISEMES.O : VISEMES.U;
      else pick = level > 0.45 ? VISEMES.AA : VISEMES.L;
      return { v: pick, amp: level };
    }

    return {
      speakText: speakText,
      attachAudio: attachAudio,
      isSpeaking: function () { return mode !== null; },
      stop: function () { mode = null; seq = null; current = VISEMES.REST; },
      duration: function () { return duration; },

      /* -> the mouth parameter overrides for this frame, or null when silent */
      step: function (now) {
        if (mode === 'audio' && analyser) {
          var r = analyse();
          var amp = Math.min(1, r.amp * 2.1);
          return {
            mouthOpen: r.v.mouthOpen * amp,
            mouthWidth: NS.lerp(0.5, r.v.mouthWidth, amp),
            mouthPurse: r.v.mouthPurse * amp,
            teeth: r.v.teeth * amp
          };
        }

        if (mode === 'text' && seq) {
          var t = now - startedAt;
          if (t > duration) {
            mode = null; seq = null;
            if (onEnd) { var f = onEnd; onEnd = null; f(); }
            return null;
          }
          var cur = null;
          for (var i = 0; i < seq.length; i++) {
            if (t >= seq[i].t && t < seq[i].t + seq[i].dur) { cur = seq[i]; break; }
          }
          if (!cur) return { mouthOpen: 0.03, mouthWidth: 0.5, mouthPurse: 0.05, teeth: 0 };

          /* an envelope inside each syllable, so it opens and closes rather
             than snapping between held shapes */
          var k = (t - cur.t) / cur.dur;
          var env = Math.sin(Math.min(1, Math.max(0, k)) * Math.PI);
          env = Math.pow(env, 0.55) * cur.stress;
          var v = VISEMES[cur.viseme];
          return {
            mouthOpen: v.mouthOpen * env,
            mouthWidth: NS.lerp(0.5, v.mouthWidth, env),
            mouthPurse: v.mouthPurse * env,
            teeth: v.teeth * env
          };
        }
        return null;
      }
    };
  };

})(NS);
