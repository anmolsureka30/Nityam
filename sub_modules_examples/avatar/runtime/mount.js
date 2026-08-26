/* mountAvatar(container, options) -> handle
 *
 * The public API, and the only thing the rest of Nityam should ever touch:
 *
 *     const tutor = Nityam.mountAvatar(el, { size: 260 });
 *     tutor.setState('listening');
 *     tutor.say("So what do you think decides the range?");
 *     tutor.react('encouraging');            // a transient beat
 *     tutor.attachAudio(audioElement);       // real TTS -> real lip sync
 *
 * Note what is NOT in here: any drawing. Swap runtime/rig.js for a Rive board
 * or a 3D head with ARKit blendshapes and everything below is unchanged,
 * because the rig's parameter names are the contract. */
(function (NS) {

  /* Conversational states, which are orthogonal to emotion. A tutor can be
     listening AND concerned, or speaking AND delighted. */
  var STATE_EMOTION = {
    idle: 'neutral',
    listening: 'listening',
    thinking: 'thinking',
    speaking: 'explaining'
  };

  NS.mountAvatar = function (container, opts) {
    opts = opts || {};
    container.innerHTML = '';
    container.classList.add('nty-avatar');

    var canvas = document.createElement('canvas');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Nityam, your tutor');
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    container.appendChild(canvas);
    var ctx = canvas.getContext('2d');

    var emo = NS.createEmotionEngine();
    var speech = NS.createSpeechEngine();
    var state = 'idle';
    var raf = null, last = 0, running = true, clock = 0;
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function resize() {
      var dpr = window.devicePixelRatio || 1;
      var w = container.clientWidth || opts.size || 260;
      var h = container.clientHeight || Math.round((opts.size || 260) * NS.DESIGN.h / NS.DESIGN.w);
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return { w: w, h: h };
    }
    var size = resize();
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(function () { size = resize(); }).observe(container);
    }

    /* One step of the whole avatar, at an explicit time. The RAF loop is just
       a caller of this — a host that owns its own loop (or a test that needs
       deterministic frames) can drive it directly instead. */
    function tick(now) {
      if (now == null) now = performance.now() / 1000;
      var dt = last ? Math.min(0.05, now - last) : 0.016;
      last = now; clock = now;

      /* Speech drives the mouth; the emotion drives everything else. They
         layer rather than fight, because the mouth targets are overrides
         into the same spring system. */
      var mouth = speech.step(now);
      if (mouth && state !== 'speaking') setState('speaking');
      if (!mouth && state === 'speaking') setState(prevState === 'speaking' ? 'idle' : prevState);

      var p = emo.step(dt, now, mouth);
      if (reduced) { p = Object.assign({}, p, { bounce: 0, breathe: 0.25 }); }
      NS.draw(ctx, p, { width: size.w, height: size.h });
      return p;
    }

    function frame(ms) {
      if (!running) return;
      tick(ms / 1000);
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    var prevState = 'idle';
    function setState(s) {
      if (!STATE_EMOTION[s]) { console.warn('[nityam:avatar] unknown state: ' + s); return false; }
      if (s === state) return true;
      if (s !== 'speaking') prevState = s;
      state = s;
      /* a transient reaction outranks the state's own resting face */
      if (emo.emotion() === emo.baseEmotion()) emo.set(STATE_EMOTION[s]);
      else emo.set(emo.emotion());
      return true;
    }

    return {
      /* conversational state: idle | listening | thinking | speaking */
      setState: setState,
      state: function () { return state; },

      /* hold an emotion until told otherwise */
      setEmotion: function (name) { return emo.set(name); },

      /* a beat that reverts on its own — "good job", a flash of surprise */
      react: function (name, seconds) { return emo.set(name, { hold: seconds || 2.2 }); },

      emotion: emo.emotion,
      emotions: NS.emotionNames,

      /* speak without audio: the mouth is driven by the words themselves */
      say: function (text, o) {
        o = o || {};
        setState('speaking');
        var d = speech.speakText(text, {
          now: clock,                     // the clock tick() is being driven with
          syllablesPerSecond: o.rate,
          onEnd: function () { setState(o.thenListen === false ? 'idle' : 'listening'); if (o.onEnd) o.onEnd(); }
        });
        return d;
      },

      /* speak WITH audio: real TTS in, real visemes out */
      attachAudio: function (source) {
        var ok = speech.attachAudio(source);
        if (ok) setState('speaking');
        return ok;
      },

      stopSpeaking: function () { speech.stop(); setState('listening'); },
      isSpeaking: speech.isSpeaking,

      /* Drive one frame yourself, at an explicit time in seconds. Lets a host
         sync the avatar to its own clock, and makes the whole thing testable. */
      tick: tick,

      /* escape hatch for one-off poses */
      nudge: emo.nudge,
      params: function () { return emo.params; },

      destroy: function () {
        running = false;
        if (raf) cancelAnimationFrame(raf);
        container.innerHTML = '';
      }
    };
  };

})(window.Nityam = window.Nityam || {});
