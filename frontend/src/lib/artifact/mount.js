/* Copied from sub_modules_examples/artifact_generator/runtime/ with one edit:
 * the IIFE receives the local NS below instead of window.Nityam. */
import { NS } from "./ns.js";

/* mountArtifact(ir, container, options) -> handle
 *
 * The single entry point. This proof of concept calls it from a standalone HTML
 * shell; the Nityam app calls the identical function from React:
 *
 *     useEffect(() => {
 *       const a = Nityam.mountArtifact(ir, ref.current, {
 *         themes, theme: student.interest,
 *         onEvidence: e => agent.updateStudentMemory(e)
 *       });
 *       return () => a.destroy();
 *     }, [ir]);
 *
 * Same runtime, same IR, two shells. */
(function (NS) {

  var SETTLE_MS = 380;

  NS.mountArtifact = function (ir, container, opts) {
    opts = opts || {};
    var themes = opts.themes || { plain: { label: 'Plain' } };
    var themeKey = themes[opts.theme] ? opts.theme : Object.keys(themes)[0];
    var theme = themes[themeKey];

    var state = NS.defaultState(ir);
    var snapshots = [];
    var timers = {};
    var R, probes;
    var answered = {};          // questionId -> chosen option (survives a rebuild)
    var evidenceLog = [];       // every event this session, so a rebuild can restore it
    var anim = { playing: false, u: 0, burst: 0, t0: 0, dur: 1 };
    var raf = null;

    function frame() { return NS.evaluate(ir, state, theme); }

    /* ── draw ─────────────────────────────────────────────────────────── */
    function redraw() {
      var f = frame();
      NS.drawScene(R.canvas, ir, f, snapshots, theme, anim);
      NS.updateReadouts(R, f);
      NS.updateAnnotations(ir, R, f, theme);
      for (var id in R.sliders) {
        var s = R.sliders[id], v = state[s.spec.bind.split('.')[1]];
        if (parseFloat(s.input.value) !== v) s.input.value = v;
        s.badge.textContent = NS.fill(s.spec.display || '{{value}}', theme, v);
      }
      if (R.pins) {
        var cap = (ir.controls.filter(function (c) { return c.action === 'snapshot'; })[0] || {}).max || 3;
        R.pins.textContent = snapshots.length ? snapshots.length + '/' + cap + ' pinned' : '';
      }
      return f;
    }

    /* ── animation: fly the projectile along its own trajectory ───────── */
    function tick(ts) {
      if (!anim.t0) anim.t0 = ts;
      var e = (ts - anim.t0) / 1000;
      if (anim.playing) {
        anim.u = Math.min(1, e / anim.dur);
        if (anim.u >= 1) { anim.playing = false; anim.u = 1; }
      }
      if (anim.burst > 0) anim.burst = Math.max(0, anim.burst - 0.018);
      redraw();
      if (anim.playing || anim.burst > 0) raf = requestAnimationFrame(tick);
      else raf = null;
    }
    function play() {
      var tof = frame().kernel.time_of_flight || 1;
      anim.playing = true; anim.u = 0; anim.t0 = 0;
      anim.dur = Math.min(2.2, Math.max(0.75, tof * 0.42));   // real-ish, never tedious
      if (!raf) raf = requestAnimationFrame(tick);
    }
    function celebrate(msg) {
      anim.burst = 1; anim.t0 = 0;
      if (!raf) raf = requestAnimationFrame(tick);
      if (opts.toast) {
        opts.toast.innerHTML = R.SVG.check + '<span></span>';
        opts.toast.lastChild.textContent = msg;
        opts.toast.classList.add('on');
        clearTimeout(timers._toast);
        timers._toast = setTimeout(function () { opts.toast.classList.remove('on'); }, 3600);
      }
    }

    /* ── evidence ─────────────────────────────────────────────────────── */

    /* Students should not read `artifact.discovered_optimum`. Probes carry a
       `note` for the agent; this turns an event into one plain sentence. */
    function humanise(e) {
      if (e.student_text) return e.student_text;
      switch (e.event) {
        case 'artifact.explored':
          var k = Object.keys(e.payload);
          return 'You tried ' + k.map(function (r) {
            return r.split('.')[1] + ' ' + e.payload[r];
          }).join(', ') + '.';
        case 'artifact.discovered_optimum':
          return 'You found the best setting by testing it yourself — that sticks better than being told.';
        case 'artifact.misconception_behavior':
          return 'You have been changing one thing only. Try the other slider and see what happens.';
        case 'assessment.answered':
          return e.payload.correct ? 'Checkpoint correct.' : 'Not quite — worth another look at the graph.';
        default:
          return e.note || e.event;
      }
    }

    function emitEvidence(e) {
      evidenceLog.push(e);
      renderEvidence(e);
      updateMastery();
      if (e.event === 'artifact.discovered_optimum') celebrate('Nice — you worked that out yourself.');
      if (e.event === 'assessment.answered' && e.payload.correct) celebrate('Checkpoint cleared.');
      if (opts.onEvidence) opts.onEvidence(e);
      console.log('[nityam:evidence]', e.event, e);
      refreshGates();
    }

    function renderEvidence(e) {
      var empty = R.feed.querySelector('.empty');
      if (empty) empty.remove();
      var row = document.createElement('div');
      row.className = 'ev' + (e.misconception ? ' warn' : (/discovered|correct/.test(e.event) || (e.payload && e.payload.correct) ? ' good' : ''));
      var ic = document.createElement('div');
      ic.className = 'ev-ic';
      ic.innerHTML = e.misconception ? R.SVG.idea : (/discovered/.test(e.event) ? R.SVG.check : '·');
      row.appendChild(ic);
      var b = document.createElement('div'); b.className = 'ev-b';
      var t = document.createElement('div'); t.className = 'ev-t';
      t.textContent = humanise(e);
      b.appendChild(t);
      var raw = document.createElement('div'); raw.className = 'ev-raw';
      raw.textContent = e.event + ' ' + JSON.stringify(e.payload) +
        (e.concept ? '  concept=' + e.concept : '') + (e.misconception ? '  misconception=' + e.misconception : '');
      b.appendChild(raw);
      row.appendChild(b);
      R.feed.insertBefore(row, R.feed.firstChild);
    }

    /* A visible stand-in for update_student_memory(). In the real app the
       agent owns this number; here we approximate it from the evidence. */
    function updateMastery() {
      var m = 0;
      evidenceLog.forEach(function (e) {
        if (e.event === 'artifact.explored') m += 8;
        else if (e.event === 'artifact.discovered_optimum') m += 34;
        else if (e.event === 'assessment.answered') m += e.payload.correct ? 30 : -6;
        else if (e.event === 'artifact.misconception_behavior') m -= 5;
      });
      m = Math.max(0, Math.min(100, Math.round(m)));
      R.bar.fill.style.width = m + '%';
      R.bar.label.textContent = m + '%';
    }

    /* ── checkpoint ───────────────────────────────────────────────────── */
    function refreshGates() {
      if (!R.check) return;
      var q = ir.assessment[0];
      var open = !q.gate || probes.count(q.gate.probe) >= (q.gate.count_gte || 1);
      if (!open || !R.check.classList.contains('hide')) return;
      R.check.classList.remove('hide');
      buildQuestion(q);
      if (answered[q.id] !== undefined) markAnswer(q, answered[q.id], R.check.querySelector('.opts'));
    }

    function buildQuestion(q) {
      R.check.innerHTML = '';
      var t = document.createElement('div'); t.className = 'ttl'; t.textContent = 'Checkpoint';
      R.check.appendChild(t);
      var p = document.createElement('p'); p.className = 'q'; p.textContent = NS.fill(q.prompt, theme);
      R.check.appendChild(p);
      var row = document.createElement('div'); row.className = 'opts';
      q.options.forEach(function (o) {
        var b = document.createElement('button');
        b.className = 'opt'; b.textContent = o + (q.unit || ''); b.dataset.v = o;
        b.onclick = function () { answered[q.id] = o; markAnswer(q, o, row); emitAnswer(q, o); };
        row.appendChild(b);
      });
      R.check.appendChild(row);
      var fb = document.createElement('div'); fb.className = 'fb';
      R.check.appendChild(fb);
    }

    function markAnswer(q, chosen, row) {
      var correct = chosen === q.expected;
      if (row) Array.prototype.forEach.call(row.children, function (b) {
        b.disabled = true;
        var v = parseFloat(b.dataset.v);
        if (v === q.expected) b.classList.add('ok');
        else if (v === chosen) b.classList.add('bad');
      });
      var fb = R.check.querySelector('.fb');
      if (fb) {
        fb.className = 'fb ' + (correct ? 'ok' : 'bad');
        fb.innerHTML = (correct ? R.SVG.check : R.SVG.cross) + '<span></span>';
        fb.lastChild.textContent = correct ? (q.explain_correct || 'Correct.') : (q.explain_wrong || 'Not quite.');
      }
      return correct;
    }

    function emitAnswer(q, chosen) {
      var correct = chosen === q.expected;
      emitEvidence({
        t: Date.now(), probe: q.id, event: 'assessment.answered',
        concept: q.concept || null,
        misconception: correct ? null : (q.diagnose || {})[String(chosen)] || null,
        note: correct ? 'Correct after exploration.' : 'Incorrect - diagnosis attached.',
        payload: { chosen: chosen, expected: q.expected, correct: correct }
      });
    }

    /* ── handlers ─────────────────────────────────────────────────────── */
    var h = {
      themes: themes, themeKey: themeKey, theme: theme,
      eyebrow: ir.intent.eyebrow || 'Explore',

      onControl: function (c, value) {
        state[c.bind.split('.')[1]] = value;
        anim.playing = false;
        redraw();
        clearTimeout(timers[c.id]);
        timers[c.id] = setTimeout(function () { probes.onSettle(c.id, frame()); }, SETTLE_MS);
      },

      onAction: function (c) {
        if (c.action === 'snapshot') {
          snapshots.push({ frame: frame(), state: Object.assign({}, state) });
          while (snapshots.length > (c.max || 3)) snapshots.shift();
        } else if (c.action === 'clear_snapshots') {
          snapshots = [];
        }
        redraw();
      },

      onPlay: play,

      onTheme: function (k) {
        themeKey = k; theme = themes[k]; h.theme = theme; h.themeKey = k;
        R = NS.buildDOM(ir, container, h);
        redraw();
        evidenceLog.forEach(renderEvidence);   // oldest first -> newest ends up on top
        updateMastery();
        refreshGates();
      }
    };

    R = NS.buildDOM(ir, container, h);
    probes = NS.createProbeEngine(ir, emitEvidence);
    redraw();
    updateMastery();
    window.addEventListener('resize', redraw);
    setTimeout(play, 380);      // one launch on load, so the artifact reads as alive

    /* Kernel parity: the JS kernel must reproduce what the Python kernel
       produced at build time. Turns silent drift into a visible failure. */
    if (opts.parity) {
      var worst = 0;
      opts.parity.forEach(function (v) {
        var got = NS.KERNELS[ir.kernel](v.in);
        for (var k in v.out) worst = Math.max(worst, Math.abs(got[k] - v.out[k]));
      });
      console.log('[nityam:parity] max |python - js| = ' + worst.toExponential(2) +
                  (worst < 1e-9 ? '  OK' : '  *** KERNEL DRIFT ***'));
      if (opts.onParity) opts.onParity(worst);
    }

    return {
      destroy: function () {
        window.removeEventListener('resize', redraw);
        if (raf) cancelAnimationFrame(raf);
        container.innerHTML = '';
      },
      play: play,
      getState: function () { return Object.assign({}, state); },
      getEvidence: function () { return evidenceLog.slice(); },
      getProbeState: function () { return probes.state(); }
    };
  };

})(NS);
