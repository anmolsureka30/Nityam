/* Emotions, and the engine that moves between them.
 *
 * An emotion is just a partial set of target values over the rig parameters.
 * Anything it doesn't mention stays wherever the previous emotion left it,
 * which is why blends look natural rather than snapping through a neutral pose.
 *
 * Each parameter has its own spring stiffness: eyes and mouth are quick, the
 * head is slow and heavy. Getting those speeds right is most of what separates
 * "alive" from "puppet". */
(function (NS) {

  /* ── the emotions ────────────────────────────────────────────────────
     Chosen for TUTORING, not for a generic emotion wheel. Note there is no
     "sad" and no "angry": a tutor is never disappointed in a student. The
     nearest thing is `gentle` — sympathetic, still on your side.           */
  var EMOTIONS = {
    neutral: {
      browRaise: 0, browInner: 0, browAsym: 0,
      eyeOpen: 1, eyeSquint: 0.05, lookX: 0, lookY: 0,
      mouthOpen: 0.04, mouthWidth: 0.5, mouthCurve: 0.2, mouthPurse: 0, teeth: 0,
      cheekRaise: 0.05, blush: 0, headTilt: 0, headNod: 0, lean: 0, bounce: 0
    },

    listening: {
      browRaise: 0.4, browInner: 0.15, browAsym: 0.2,
      eyeOpen: 1.1, eyeSquint: 0.1, lookX: 0, lookY: 0,
      mouthOpen: 0.03, mouthWidth: 0.46, mouthCurve: 0.34, mouthPurse: 0.05, teeth: 0,
      cheekRaise: 0.15, blush: 0, headTilt: 0.3, headNod: 0.14, lean: 0.4, bounce: 0
    },

    thinking: {
      browRaise: -0.25, browInner: -0.6, browAsym: 0.55,
      eyeOpen: 0.8, eyeSquint: 0.25, lookX: 0.7, lookY: -0.75,
      mouthOpen: 0.02, mouthWidth: 0.34, mouthCurve: -0.05, mouthPurse: 0.6, teeth: 0,
      cheekRaise: 0, blush: 0, headTilt: -0.24, headNod: -0.16, lean: -0.2, bounce: 0
    },

    explaining: {
      browRaise: 0.3, browInner: -0.1, browAsym: 0.15,
      eyeOpen: 1.04, eyeSquint: 0.12, lookX: 0, lookY: 0,
      mouthOpen: 0.3, mouthWidth: 0.6, mouthCurve: 0.34, mouthPurse: 0, teeth: 0.5,
      cheekRaise: 0.2, blush: 0, headTilt: 0.08, headNod: 0, lean: 0.2, bounce: 0
    },

    /* the "good job" face — a real smile reaches the EYES, so eyeSquint and
       cheekRaise do more work here than mouth width does */
    encouraging: {
      browRaise: 0.6, browInner: 0.2, browAsym: 0,
      eyeOpen: 0.85, eyeSquint: 0.85, lookX: 0, lookY: 0,
      mouthOpen: 0.24, mouthWidth: 0.86, mouthCurve: 1, mouthPurse: 0, teeth: 0.8,
      cheekRaise: 0.9, blush: 0.35, headTilt: 0.16, headNod: 0.22, lean: 0.3, bounce: 0.12
    },

    excited: {
      browRaise: 1, browInner: 0.15, browAsym: 0,
      eyeOpen: 1.3, eyeSquint: 0.4, lookX: 0, lookY: 0,
      mouthOpen: 0.72, mouthWidth: 0.95, mouthCurve: 0.95, mouthPurse: 0, teeth: 0.95,
      cheekRaise: 1, blush: 0.55, headTilt: -0.12, headNod: -0.22, lean: 0.5, bounce: 0.75
    },

    curious: {
      browRaise: 0.45, browInner: -0.15, browAsym: 1,
      eyeOpen: 1.14, eyeSquint: 0.05, lookX: 0.2, lookY: 0,
      mouthOpen: 0.04, mouthWidth: 0.38, mouthCurve: 0.4, mouthPurse: 0.4, teeth: 0,
      cheekRaise: 0.15, blush: 0, headTilt: 0.55, headNod: 0.05, lean: 0.3, bounce: 0
    },

    surprised: {
      browRaise: 1, browInner: 0.5, browAsym: 0,
      eyeOpen: 1.38, eyeSquint: 0, lookX: 0, lookY: 0,
      mouthOpen: 0.62, mouthWidth: 0.28, mouthCurve: 0.05, mouthPurse: 0.75, teeth: 0.2,
      cheekRaise: 0, blush: 0.15, headTilt: 0.04, headNod: -0.3, lean: -0.3, bounce: 0
    },

    /* NOT disappointment. A tutor is never disappointed in a student — this
       is warm, sympathetic, "let's look again". */
    gentle: {
      browRaise: 0.2, browInner: 1, browAsym: 0.15,
      eyeOpen: 0.86, eyeSquint: 0.3, lookX: 0, lookY: 0.1,
      mouthOpen: 0.02, mouthWidth: 0.42, mouthCurve: -0.35, mouthPurse: 0.15, teeth: 0,
      cheekRaise: 0.1, blush: 0, headTilt: 0.42, headNod: 0.2, lean: 0.24, bounce: 0
    },

    proud: {
      browRaise: 0.35, browInner: 0.25, browAsym: 0,
      eyeOpen: 0.82, eyeSquint: 0.75, lookX: 0, lookY: 0,
      mouthOpen: 0.1, mouthWidth: 0.7, mouthCurve: 0.85, mouthPurse: 0, teeth: 0.4,
      cheekRaise: 0.85, blush: 0.3, headTilt: -0.1, headNod: -0.3, lean: 0.05, bounce: 0
    }
  };
  NS.EMOTIONS = EMOTIONS;
  NS.emotionNames = function () { return Object.keys(EMOTIONS); };

  /* ── per-parameter spring constants ──────────────────────────────────
     [stiffness, damping]. Light features settle fast; the head is heavy and
     lags, which is exactly what makes the motion read as a body rather than
     a set of sliders.                                                     */
  var SPRING = {
    _default:  [0.11, 0.76],
    /* the mouth must keep up with speech, so it stays fast */
    mouthOpen: [0.55, 0.48],
    mouthWidth:[0.34, 0.60],
    mouthPurse:[0.38, 0.58],
    teeth:     [0.30, 0.62],
    /* eyes are quick — a blink or a widen is near-instant */
    eyeOpen:   [0.42, 0.55],
    lookX:     [0.30, 0.62],
    lookY:     [0.30, 0.62],
    /* the expression carriers are slower: a face takes ~0.3s to change its
       mind, and anything quicker reads as a cut rather than a feeling */
    eyeSquint: [0.13, 0.74],
    mouthCurve:[0.11, 0.76],
    browRaise: [0.12, 0.75],
    browInner: [0.11, 0.76],
    browAsym:  [0.10, 0.78],
    headTilt:  [0.09, 0.80],
    headTurn:  [0.09, 0.80],
    headNod:   [0.10, 0.78],
    lean:      [0.08, 0.82],
    bounce:    [0.26, 0.55],
    cheekRaise:[0.12, 0.75],
    blush:     [0.06, 0.86]
  };

  NS.createEmotionEngine = function (opts) {
    opts = opts || {};
    var cur = NS.newParams();          // where we are
    var vel = NS.newParams();          // spring velocity
    var target = NS.newParams();       // where we're heading
    for (var k in vel) vel[k] = 0;

    var emotion = 'neutral';
    var holdLeft = 0;                  // seconds remaining on a transient emotion
    var baseEmotion = 'neutral';       // what to fall back to

    apply(EMOTIONS.neutral);

    function apply(e) {
      for (var k in e) if (k in target) target[k] = e[k];
    }

    /* ── idle behaviour ────────────────────────────────────────────────
       Without this the avatar is a corpse with a moving mouth. Blinks,
       breath, micro-saccades and slow head drift are doing more work for
       believability than any single expression.                          */
    var t0 = 0, nextBlink = 1.4, blinkPhase = -1, blinkQueue = 0;
    var nextSaccade = 2.0, saccX = 0, saccY = 0;
    var driftSeed = Math.random() * 100;

    function idle(dt, now, speaking) {
      // breathing
      target.breathe = (now * 0.22) % 1;

      // blinking — occasionally a double blink, which humans do constantly
      if (blinkPhase >= 0) {
        blinkPhase += dt * 7.5;
        var b = blinkPhase < 1 ? blinkPhase : 2 - blinkPhase;
        cur.eyeOpen = Math.min(cur.eyeOpen, Math.max(0, target.eyeOpen * (1 - b)));
        if (blinkPhase >= 2) {
          blinkPhase = -1;
          if (blinkQueue > 0) { blinkQueue--; blinkPhase = 0; }
          else nextBlink = now + 1.8 + Math.random() * 4.2;
        }
      } else if (now > nextBlink) {
        blinkPhase = 0;
        if (Math.random() < 0.28) blinkQueue = 1;
      }

      // micro-saccades: the eyes are never perfectly still
      if (now > nextSaccade) {
        saccX = (Math.random() - 0.5) * 0.34;
        saccY = (Math.random() - 0.5) * 0.22;
        nextSaccade = now + 0.7 + Math.random() * 2.4;
      }

      // slow head drift, so a held pose never freezes
      var d = driftSeed + now * 0.35;
      var driftTurn = Math.sin(d) * 0.09 + Math.sin(d * 0.37) * 0.05;
      var driftTilt = Math.sin(d * 0.53 + 1.1) * 0.05;
      var driftNod = Math.sin(d * 0.41 + 2.3) * 0.05;

      return { saccX: saccX, saccY: saccY,
               driftTurn: driftTurn, driftTilt: driftTilt, driftNod: driftNod };
    }

    return {
      /* set(name)                      hold it
         set(name, {hold: 1.8})         revert to the base emotion after 1.8s  */
      set: function (name, o) {
        if (!EMOTIONS[name]) { console.warn('[nityam:avatar] unknown emotion: ' + name); return false; }
        o = o || {};
        emotion = name;
        apply(EMOTIONS[name]);
        if (o.hold) holdLeft = o.hold;              // counted down in step(), so
        else { holdLeft = 0; baseEmotion = name; }  // it never depends on a clock
        return true;
      },
      emotion: function () { return emotion; },
      baseEmotion: function () { return baseEmotion; },

      /* one-off nudges layered on top of the current emotion */
      nudge: function (patch) { for (var k in patch) if (k in target) target[k] = patch[k]; },

      params: cur,
      target: target,

      step: function (dt, now, overrides) {
        if (holdLeft > 0) {
          holdLeft -= dt;
          if (holdLeft <= 0) { holdLeft = 0; emotion = baseEmotion; apply(EMOTIONS[baseEmotion]); }
        }

        var idl = idle(dt, now, false);

        // speech and other live drivers win over the emotion's own targets
        if (overrides) for (var k in overrides) if (k in target) target[k] = overrides[k];

        for (var p in target) {
          if (p === 'breathe') { cur[p] = target[p]; continue; }
          var sp = SPRING[p] || SPRING._default;
          var extra = 0;
          if (p === 'lookX') extra = idl.saccX;
          else if (p === 'lookY') extra = idl.saccY;
          else if (p === 'headTurn') extra = idl.driftTurn;
          else if (p === 'headTilt') extra = idl.driftTilt;
          else if (p === 'headNod') extra = idl.driftNod;

          var goal = target[p] + extra;
          vel[p] = (vel[p] + (goal - cur[p]) * sp[0]) * sp[1];
          cur[p] += vel[p];
        }

        // the blink is applied AFTER the spring so it always fully closes
        if (blinkPhase >= 0) {
          var bb = blinkPhase < 1 ? blinkPhase : 2 - blinkPhase;
          cur.eyeOpen *= Math.max(0, 1 - bb * 1.05);
        }
        return cur;
      }
    };
  };

})(typeof window !== 'undefined' ? (window.Nityam = window.Nityam || {}) : (module.exports = {}));
