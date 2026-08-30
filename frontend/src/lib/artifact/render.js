/* Copied from sub_modules_examples/artifact_generator/runtime/ with one edit:
 * the IIFE receives the local NS below instead of window.Nityam. */
import { NS } from "./ns.js";

/* The renderer: frame -> pixels + DOM.
 *
 * Hand-written, deterministic, identical for every artifact. The IR chooses
 * which layers to stack and what to bind them to; it has no say over layout,
 * colour or type. That is a deliberate trade - less visual variety, total
 * predictability, and one place to make everything look good.
 *
 * Colour rule: data marks use fixed, CVD-validated colours (categorical slots
 * 1-3). The THEME tints the world - sky, story, icon - and never the data. */
(function (NS) {

  var SVG = {
    play:  '<svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor"><path d="M3.5 1.8v9.4a.6.6 0 0 0 .92.5l7.2-4.7a.6.6 0 0 0 0-1L4.42 1.3a.6.6 0 0 0-.92.5z"/></svg>',
    pin:   '<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M7 8.5V13"/><path d="M4 1h6l-.8 4.2L11 7.2v1.3H3V7.2l1.8-2z"/></svg>',
    idea:  '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 13h4M6.5 15h3"/><path d="M8 1a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.7.6 1.1v.2h4v-.2c0-.4.2-.8.6-1.1A4.5 4.5 0 0 0 8 1z"/></svg>',
    check: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M13 4.5L6.2 11.5 3 8.3"/></svg>',
    cross: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M11.5 4.5l-7 7M4.5 4.5l7 7"/></svg>'
  };

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  }
  function niceStep(span, target) {
    var raw = span / (target || 4), mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), n = raw / mag;
    return (n >= 5 ? 5 : n >= 2 ? 2 : 1) * mag;
  }
  function roundRect(g, x, y, w, h, r) {
    g.beginPath();
    g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }

  /* ─────────────────────────────────────────────────────────── the scene */

  /* The scene the axes are sized for — fixed while the student explores.
   *
   * WHY NOT JUST SWEEP EVERYTHING. Range goes as u squared, so sweeping a
   * 5-to-40 speed slider gives an envelope four times wider than any
   * trajectory the student is actually looking at: the axes would be rock
   * steady and the curve would be a scribble in the corner. Measured on the
   * real projectile IR — envelope x=175 against a default path of x=41.
   *
   * So a control is only swept if doing so does not blow the scale. Angle
   * qualifies: the whole point of this artifact is that range peaks at 45
   * degrees, and you cannot see a peak if the ruler stretches to fit every
   * value as you drag. Speed does not, so it is PINNED at its current value
   * and becomes part of the cache key — change the speed and the axes resize
   * once, which is honest, because you have changed the size of the problem.
   */
  var SWEEP_INFLATION_LIMIT = 2.5;

  function pathExtent(ir, state, theme) {
    var x = 1, y = 1;
    var path = NS.evaluate(ir, state, theme).kernel.path || [];
    path.forEach(function (pt) {
      if (pt.x > x) x = pt.x;
      if (pt.y > y) y = pt.y;
    });
    return { x: x, y: y };
  }

  function sampled(def, i, n) {
    return def.min + (def.max - def.min) * (i / (n - 1));
  }

  function worldBounds(ir, frame) {
    var current = frame.state || NS.defaultState(ir);

    try {
      var ranged = [];
      for (var k in ir.state) {
        var v = ir.state[k];
        if (v && typeof v.min === 'number' && typeof v.max === 'number' && v.max > v.min) {
          ranged.push(k);
        }
      }
      if (!ranged.length) throw new Error('nothing to sweep');

      var now = pathExtent(ir, current, frame.theme);

      // Which controls can be swept without the curve shrinking to nothing.
      var sweep = ranged.filter(function (name) {
        var widest = now.x;
        for (var i = 0; i < 5; i++) {
          var probe = Object.assign({}, current);
          probe[name] = sampled(ir.state[name], i, 5);
          var e = pathExtent(ir, probe, frame.theme);
          if (e.x > widest) widest = e.x;
        }
        return widest <= now.x * SWEEP_INFLATION_LIMIT;
      });
      if (!sweep.length) throw new Error('every control blows the scale');

      // Pinned controls are part of the key: the axes hold still while the
      // swept ones move, and resize once when a pinned one changes.
      var key = ranged
        .filter(function (n) { return sweep.indexOf(n) < 0; })
        .map(function (n) { return n + '=' + current[n]; })
        .join(',');
      if (ir.__bounds && ir.__boundsKey === key) return ir.__bounds;

      var per = sweep.length <= 2 ? 7 : (sweep.length === 3 ? 5 : 3);
      var total = Math.pow(per, sweep.length);
      if (total > 128) throw new Error('sweep too large');

      var xmax = 1, ymax = 1;
      for (var c = 0; c < total; c++) {
        var state = Object.assign({}, current), n = c;
        for (var j = 0; j < sweep.length; j++) {
          state[sweep[j]] = sampled(ir.state[sweep[j]], n % per, per);
          n = Math.floor(n / per);
        }
        var ext = pathExtent(ir, state, frame.theme);
        if (ext.x > xmax) xmax = ext.x;
        if (ext.y > ymax) ymax = ext.y;
      }

      // Same headroom the per-frame version used, so nothing downstream had
      // to change.
      xmax *= 1.07;
      ymax = Math.max(ymax * 1.25, xmax * 0.30);
      ir.__bounds = { x: xmax, y: ymax };
      ir.__boundsKey = key;
      return ir.__bounds;
    } catch (e) {
      // A mis-sized grid is worth far less than a broken artifact: fall back
      // to the old per-frame behaviour rather than failing to draw.
      var f = pathExtent(ir, current, frame.theme);
      return { x: f.x * 1.07, y: Math.max(f.y * 1.25, f.x * 1.07 * 0.30) };
    }
  }

  NS.drawScene = function (canvas, ir, frame, snapshots, theme, anim) {
    var dpr = window.devicePixelRatio || 1;
    var W = canvas.clientWidth, H = canvas.clientHeight;
    if (!W || !H) return;
    canvas.width = W * dpr; canvas.height = H * dpr;
    var g = canvas.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    var C = {
      s1: cssVar('--s1'), s2: cssVar('--s2'), s3: cssVar('--s3'),
      ink: cssVar('--ink'), ink2: cssVar('--ink-2'), ink3: cssVar('--ink-3'),
      grid: cssVar('--grid'), ground: cssVar('--ground'), groundLine: cssVar('--ground-line'),
      card: cssVar('--card')
    };
    var FONT = '-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif';

    var scene = ir.layers.filter(function (l) { return l.type === 'scene2d'; })[0] || {};
    var traceLayer = ir.layers.filter(function (l) { return l.type === 'trace'; })[0];
    var ghosts = ir.layers.some(function (l) { return l.type === 'trace_set'; }) ? snapshots : [];
    var vecLayer = ir.layers.filter(function (l) { return l.type === 'vector'; })[0];
    var vecSet = ir.layers.filter(function (l) { return l.type === 'vector_set'; })[0];

    /* World bounds, FIXED for the life of the artifact.
     *
     * These used to be measured off the current trajectory every frame, so
     * dragging the angle rescaled the axes underneath the curve: the gridlines
     * slid, the numbers on them changed, and the path stayed roughly the same
     * size on screen. That hides the very thing a projectile simulation exists
     * to show — that 45 degrees goes FURTHER. You cannot see further if the
     * ruler stretches to fit.
     *
     * So the envelope is computed once, from what the controls can actually
     * reach, and the curve moves within it. */
    var live = traceLayer ? (NS.resolveRef(traceLayer.points, frame) || []) : [];
    var bounds = worldBounds(ir, frame);
    var xmax = bounds.x, ymax = bounds.y;
    // A pinned ghost is real data and must never fall outside the frame, even
    // if it came from a kernel the sweep could not reach.
    ghosts.forEach(function (s) {
      s.frame.kernel.path.forEach(function (pt) {
        if (pt.x > xmax) xmax = pt.x;
        if (pt.y > ymax) ymax = pt.y;
      });
    });

    var M = { l: 58, r: 24, t: 14, b: 42 };
    var scale = Math.min((W - M.l - M.r) / xmax, (H - M.t - M.b) / ymax);  // equal aspect
    var ox = M.l, oy = H - M.b;
    function px(x, y) { return [ox + x * scale, oy - y * scale]; }
    var right = ox + xmax * scale;

    /* sky - a whisper of the theme's colour, the only place theme touches paint */
    g.clearRect(0, 0, W, H);
    var sky = g.createLinearGradient(0, 0, 0, oy);
    sky.addColorStop(0, (theme.tint || 'rgba(42,120,214,0.07)'));
    sky.addColorStop(1, 'rgba(0,0,0,0)');
    roundRect(g, 0, 0, W, H, 9); g.fillStyle = sky; g.fill();

    /* grid + axis labels - recessive */
    g.font = '11px ' + FONT; g.lineWidth = 1;
    var sx = niceStep(xmax, 5), sy = niceStep(ymax, 4);
    g.strokeStyle = C.grid;
    for (var x = sx; x <= xmax; x += sx) {
      var a = px(x, 0); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(a[0], M.t); g.stroke();
      g.fillStyle = C.ink3; g.textAlign = 'center'; g.fillText(Math.round(x), a[0], oy + 18);
    }
    for (var y = sy; y <= ymax; y += sy) {
      var c = px(0, y); g.beginPath(); g.moveTo(ox, c[1]); g.lineTo(right, c[1]); g.stroke();
      g.fillStyle = C.ink3; g.textAlign = 'right'; g.fillText(Math.round(y), ox - 9, c[1] + 4);
    }
    if (scene.x_label) { g.fillStyle = C.ink3; g.textAlign = 'right'; g.fillText(scene.x_label, right, oy + 33); }
    if (scene.y_label) { g.save(); g.translate(13, oy); g.rotate(-Math.PI / 2);
      g.fillStyle = C.ink3; g.textAlign = 'left'; g.fillText(scene.y_label, 4, 0); g.restore(); }

    /* ground */
    g.fillStyle = C.ground; g.fillRect(0, oy, W, H - oy);
    g.strokeStyle = C.groundLine; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(0, oy + .5); g.lineTo(W, oy + .5); g.stroke();
    if (scene.ground_label) {
      g.fillStyle = C.ink3; g.textAlign = 'left'; g.font = '11px ' + FONT;
      g.fillText(NS.fill(scene.ground_label, theme), 6, oy + 18);
    }

    /* pinned ghosts - neutral, dashed, DIRECT-LABELLED (identity never colour-alone) */
    ghosts.forEach(function (s) {
      g.strokeStyle = C.ink3; g.globalAlpha = .45; g.lineWidth = 1.5; g.setLineDash([5, 5]);
      g.beginPath();
      s.frame.kernel.path.forEach(function (pt, i) { var q = px(pt.x, pt.y); i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]); });
      g.stroke(); g.setLineDash([]); g.globalAlpha = 1;

      var last = s.frame.kernel.path[s.frame.kernel.path.length - 1], lp = px(last.x, last.y);
      var lbl = Math.round(s.frame.state.theta) + '°';
      g.font = '600 11px ' + FONT; g.textAlign = 'center';
      var w = g.measureText(lbl).width + 13;
      g.fillStyle = C.card; g.strokeStyle = C.groundLine; g.lineWidth = 1;
      roundRect(g, lp[0] - w / 2, lp[1] - 25, w, 18, 9); g.fill(); g.stroke();
      g.fillStyle = C.ink2; g.fillText(lbl, lp[0], lp[1] - 12);
    });

    /* the live trajectory */
    if (live.length) {
      g.strokeStyle = C.s1; g.lineWidth = 2.6; g.lineJoin = 'round'; g.lineCap = 'round';
      g.beginPath();
      live.forEach(function (pt, i) { var q = px(pt.x, pt.y); i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]); });
      g.stroke();

      /* range dimension line along the ground */
      var end = live[live.length - 1], e = px(end.x, end.y);
      g.strokeStyle = C.s1; g.globalAlpha = .32; g.lineWidth = 1.5; g.setLineDash([3, 4]);
      g.beginPath(); g.moveTo(ox, oy + 9); g.lineTo(e[0], oy + 9); g.stroke();
      g.setLineDash([]); g.globalAlpha = 1;
      [ox, e[0]].forEach(function (t) {
        g.strokeStyle = C.s1; g.globalAlpha = .5; g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(t, oy + 5); g.lineTo(t, oy + 13); g.stroke(); g.globalAlpha = 1;
      });

      /* the projectile - animated along the path, or resting at the landing point */
      var p = end;
      if (anim && anim.playing) {
        var i = Math.min(live.length - 1, Math.floor(anim.u * (live.length - 1)));
        p = live[i];
        /* motion trail */
        g.strokeStyle = C.s1; g.globalAlpha = .22; g.lineWidth = 6; g.lineCap = 'round';
        g.beginPath();
        for (var j = Math.max(0, i - 9); j <= i; j++) { var q = px(live[j].x, live[j].y); j === Math.max(0, i - 9) ? g.moveTo(q[0], q[1]) : g.lineTo(q[0], q[1]); }
        g.stroke(); g.globalAlpha = 1;
      }
      var bp = px(p.x, p.y);
      var glyph = NS.fill(traceLayer.end_marker || '', theme);
      g.globalAlpha = .18; g.fillStyle = C.ink;
      g.beginPath(); g.ellipse(bp[0], oy - 1.5, 7, 2.5, 0, 0, Math.PI * 2); g.fill(); g.globalAlpha = 1;
      if (glyph) { g.font = '19px ' + FONT + ',"Apple Color Emoji"'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(glyph, bp[0], bp[1] - 7); g.textBaseline = 'alphabetic'; }
      else { g.fillStyle = C.s1; g.strokeStyle = C.card; g.lineWidth = 2;
             g.beginPath(); g.arc(bp[0], bp[1] - 6, 6.5, 0, Math.PI * 2); g.fill(); g.stroke(); }

      /* celebration burst */
      if (anim && anim.burst > 0) {
        var lp2 = px(end.x, end.y);
        for (var k = 0; k < 12; k++) {
          var ang = (k / 12) * Math.PI * 2, d = (1 - anim.burst) * 34;
          g.globalAlpha = anim.burst * .85; g.fillStyle = k % 2 ? C.s3 : C.s1;
          g.beginPath(); g.arc(lp2[0] + Math.cos(ang) * d, lp2[1] - 6 + Math.sin(ang) * d, 2.6 * anim.burst + .6, 0, Math.PI * 2); g.fill();
        }
        g.globalAlpha = 1;
      }
    }

    /* velocity arrows */
    function arrow(x1, y1, x2, y2, col, dash, lbl, lw) {
      if (Math.abs(x2 - x1) < .8 && Math.abs(y2 - y1) < .8) return;
      g.strokeStyle = col; g.fillStyle = col; g.lineWidth = lw || 2; g.lineCap = 'round';
      g.setLineDash(dash || []);
      var ang = Math.atan2(y2 - y1, x2 - x1);
      g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2 - 6 * Math.cos(ang), y2 - 6 * Math.sin(ang)); g.stroke();
      g.setLineDash([]);
      g.beginPath(); g.moveTo(x2, y2);
      g.lineTo(x2 - 8 * Math.cos(ang - .38), y2 - 8 * Math.sin(ang - .38));
      g.lineTo(x2 - 8 * Math.cos(ang + .38), y2 - 8 * Math.sin(ang + .38));
      g.closePath(); g.fill();
      if (lbl) {
        g.font = '600 11.5px ' + FONT; g.textAlign = 'center'; g.textBaseline = 'middle';
        var lx = x2 + 15 * Math.cos(ang), ly = y2 + 15 * Math.sin(ang);
        lx = Math.max(lx, ox + 12);            // never collide with the y-axis gutter
        var w = g.measureText(lbl).width + 9;
        g.fillStyle = C.card; g.globalAlpha = .9; roundRect(g, lx - w / 2, ly - 8, w, 16, 6); g.fill(); g.globalAlpha = 1;
        g.fillStyle = col; g.fillText(lbl, lx, ly); g.textBaseline = 'alphabetic';
      }
    }

    var umax = (ir.state.u && ir.state.u.max) || 40;
    /* arrows are schematic - size them against the drawn scene, not the world */
    var K = Math.min(132, (right - ox) * 0.34) / umax;

    if (vecLayer) {
      var at = NS.resolveRef(vecLayer.at, frame) || { x: 0, y: 0 }, o = px(at.x, at.y);
      var vx = NS.resolveRef(vecLayer.components.x, frame) || 0;
      var vy = NS.resolveRef(vecLayer.components.y, frame) || 0;
      var L = vecLayer.labels || {};
      if (vecLayer.decompose) {
        arrow(o[0], o[1], o[0] + vx * K, o[1], C.s3, [4, 3], L.x || 'uₓ', 1.8);
        arrow(o[0], o[1], o[0], o[1] - vy * K, C.s2, [4, 3], L.y || 'uᵧ', 1.8);
      }
      arrow(o[0], o[1], o[0] + vx * K, o[1] - vy * K, C.ink, [], L.resultant || 'u', 2.2);
    }

    /* vector_set - velocity arrows sampled along the flight. This is what makes
       "horizontal velocity never changes" visible rather than asserted. */
    if (vecSet && live.length) {
      var n = vecSet.count || 5, K2 = (vecSet.scale || 52) / umax;
      for (var m = 0; m < n; m++) {
        var pt = live[Math.round((m + 0.5) / n * (live.length - 1))];
        var q = px(pt.x, pt.y);
        var cx = NS.resolveRef(vecSet.components.x, { state: frame.state, kernel: frame.kernel, derived: frame.derived, point: pt });
        var cy = NS.resolveRef(vecSet.components.y, { state: frame.state, kernel: frame.kernel, derived: frame.derived, point: pt });
        if (cx == null) cx = pt.vx; if (cy == null) cy = pt.vy;
        g.globalAlpha = .95;
        if (vecSet.decompose) {
          arrow(q[0], q[1], q[0] + cx * K2, q[1], C.s3, [], m === 0 ? (vecSet.labels || {}).x || 'vₓ' : '', 1.6);
          arrow(q[0], q[1], q[0], q[1] - cy * K2, C.s2, [], m === 0 ? (vecSet.labels || {}).y || 'vᵧ' : '', 1.6);
        } else {
          arrow(q[0], q[1], q[0] + cx * K2, q[1] - cy * K2, C.ink, [], '', 1.6);
        }
        g.globalAlpha = 1;
        g.fillStyle = C.s1; g.beginPath(); g.arc(q[0], q[1], 2.5, 0, Math.PI * 2); g.fill();
      }
    }
  };

  /* ────────────────────────────────────────────────────────── DOM build */

  NS.buildDOM = function (ir, root, h) {
    root.innerHTML = '';
    var R = { sliders: {}, stats: [], hero: null, annos: null, feed: null, check: null, bar: null, pins: null };
    var q0 = (ir.assessment || [])[0];

    /* top bar */
    var top = el('div', 'top');
    var brand = el('div', 'brand');
    brand.appendChild(el('div', 'dot'));
    brand.appendChild(el('b', null, 'Nityam'));
    brand.appendChild(el('i', null, '/'));
    brand.appendChild(el('span', null, (ir.intent.concept_ids[0] || '').split('.')[0].replace(/_/g, ' ')
      .replace(/^./, function (s) { return s.toUpperCase(); }) + ' · Class 11 Physics'));
    top.appendChild(brand);

    var pick = el('div', 'picker');
    pick.appendChild(el('label', null, 'Story'));
    var sel = el('select');
    Object.keys(h.themes).forEach(function (k) {
      var o = el('option', null, h.themes[k].label || k); o.value = k; sel.appendChild(o);
    });
    sel.value = h.themeKey;
    sel.onchange = function () { h.onTheme(sel.value); };
    pick.appendChild(sel);
    top.appendChild(pick);
    root.appendChild(top);

    /* lesson header - the learning outcome, in student language */
    var lesson = el('div', 'lesson');
    lesson.appendChild(el('div', 'eyebrow', h.eyebrow || 'Explore'));
    lesson.appendChild(el('h1', null, NS.fill(ir.intent.student_prompt || ir.intent.learning_outcome, h.theme)));
    if (ir.intent.student_hint) lesson.appendChild(el('p', null, NS.fill(ir.intent.student_hint, h.theme)));
    root.appendChild(lesson);

    /* stage + side */
    var grid = el('div', 'grid');
    var leftCol = el('div');
    var stage = el('div', 'card stage');
    var canvas = el('canvas');
    stage.appendChild(canvas);

    var bar = el('div', 'stagebar');
    var play = el('button', 'btn btn-primary');
    play.innerHTML = SVG.play + '<span>Launch</span>';
    play.onclick = function () { h.onPlay(); };
    bar.appendChild(play);

    ir.controls.filter(function (c) { return c.widget === 'button'; }).forEach(function (c) {
      var b = el('button', 'btn');
      b.innerHTML = (c.action === 'snapshot' ? SVG.pin : '') + '<span>' + c.label + '</span>';
      b.onclick = function () { h.onAction(c); };
      bar.appendChild(b);
      if (c.action === 'snapshot') { R.pins = el('span', 'pincount'); bar.appendChild(R.pins); }
    });
    bar.appendChild(el('div', 'spacer'));
    stage.appendChild(bar);
    leftCol.appendChild(stage);

    R.annos = el('div', 'annos');
    leftCol.appendChild(R.annos);
    grid.appendChild(leftCol);

    /* side panel */
    var side = el('aside', 'side');
    var rg = ir.layers.filter(function (l) { return l.type === 'readout_group'; })[0];
    if (rg) {
      var card = el('div', 'card pad');
      var items = rg.items.slice();
      var heroSpec = items.filter(function (i) { return i.emphasis; })[0] || items[0];
      items = items.filter(function (i) { return i !== heroSpec; });

      var hero = el('div', 'hero');
      hero.appendChild(el('div', 'hero-l', heroSpec.label));
      var hv = el('div', 'hero-v');
      hv.innerHTML = '<span>—</span>' + (heroSpec.unit ? '<u>' + heroSpec.unit + '</u>' : '');
      hero.appendChild(hv);
      card.appendChild(hero);
      R.hero = { spec: heroSpec, node: hv, num: hv.firstChild };

      items.forEach(function (it) {
        var row = el('div', 'stat');
        var l = el('span', 'stat-l');
        if (it.swatch) { var sw = el('span', 'swatch'); sw.style.background = 'var(--' + it.swatch + ')'; l.appendChild(sw); }
        l.appendChild(el('span', null, it.label));
        row.appendChild(l);
        var v = el('span', 'stat-v', '—');
        row.appendChild(v);
        card.appendChild(row);
        R.stats.push({ spec: it, node: v });
      });
      side.appendChild(card);
    }

    var cc = el('div', 'card pad');
    cc.appendChild(el('div', 'ttl', 'Controls'));
    ir.controls.filter(function (c) { return c.widget === 'slider'; }).forEach(function (c) {
      var nm = c.bind.split('.')[1], sv = ir.state[nm];
      var w = el('div', 'ctl');
      var t = el('div', 'ctl-top');
      t.appendChild(el('span', 'ctl-l', NS.fill(c.label, h.theme)));
      var badge = el('span', 'ctl-v');
      t.appendChild(badge); w.appendChild(t);
      var inp = el('input');
      inp.type = 'range'; inp.min = sv.min; inp.max = sv.max; inp.step = sv.step || 1; inp.value = sv.value;
      inp.setAttribute('aria-label', NS.fill(c.label, h.theme));
      inp.oninput = function () { h.onControl(c, parseFloat(inp.value)); };
      w.appendChild(inp);
      cc.appendChild(w);
      R.sliders[c.id] = { input: inp, badge: badge, spec: c };
    });
    side.appendChild(cc);
    grid.appendChild(side);
    root.appendChild(grid);

    /* checkpoint */
    if (q0) { R.check = el('div', 'card check hide'); root.appendChild(R.check); }

    /* what Nityam noticed */
    var nt = el('div', 'card noticed');
    var ttl = el('div', 'ttl');
    ttl.appendChild(el('span', null, 'What Nityam noticed'));
    var tog = el('label', 'toggle');
    var cb = el('input'); cb.type = 'checkbox';
    cb.onchange = function () { R.feed.classList.toggle('showraw', cb.checked); };
    tog.appendChild(cb); tog.appendChild(el('span', null, 'raw events'));
    ttl.appendChild(tog);
    nt.appendChild(ttl);

    var mw = el('div', 'mastery');
    var mt = el('div', 'mastery-top');
    mt.appendChild(el('span', null, (ir.intent.concept_ids[0] || '').replace(/[._]/g, ' ')));
    var mv = el('b', null, '0%');
    mt.appendChild(mv); mw.appendChild(mt);
    var barw = el('div', 'bar'); var fill = el('i'); barw.appendChild(fill); mw.appendChild(barw);
    nt.appendChild(mw);
    R.bar = { fill: fill, label: mv };

    R.feed = el('div', 'feed');
    R.feed.appendChild(el('div', 'empty', 'Move a slider and let go — Nityam is watching how you explore.'));
    nt.appendChild(R.feed);
    root.appendChild(nt);

    R.canvas = canvas;
    R.SVG = SVG;
    return R;
  };

  NS.updateReadouts = function (R, frame) {
    function fmt(spec) {
      var v = NS.resolveRef(spec.value, frame);
      var p = spec.precision == null ? 1 : spec.precision;
      return typeof v === 'number' ? v.toFixed(p) : '—';
    }
    if (R.hero) {
      var t = fmt(R.hero.spec);
      if (R.hero.num.textContent !== t) {
        R.hero.num.textContent = t;
        R.hero.node.classList.remove('bump'); void R.hero.node.offsetWidth; R.hero.node.classList.add('bump');
      }
    }
    R.stats.forEach(function (s) {
      s.node.textContent = fmt(s.spec) + (s.spec.unit ? ' ' + s.spec.unit : '');
    });
  };

  NS.updateAnnotations = function (ir, R, frame, theme) {
    var want = ir.layers.filter(function (l) { return l.type === 'annotation' && NS.evalCondition(l.when, frame); })
                        .map(function (l) { return NS.fill(l.text, theme); });
    var have = Array.prototype.map.call(R.annos.children, function (c) { return c.dataset.t; });
    if (want.join('|') === have.join('|')) return;      // don't re-animate on every tick
    R.annos.innerHTML = '';
    want.forEach(function (t) {
      var d = el('div', 'anno'); d.dataset.t = t;
      d.innerHTML = SVG.idea + '<span></span>';
      d.lastChild.textContent = t;
      R.annos.appendChild(d);
    });
  };

})(NS);
