/* The rig: a parameter set, and a procedural drawing of a face that reads it.
 *
 * Every expressive thing the avatar can do is a NUMBER in this list. Emotions
 * are target values for these numbers; speech drives three of them; idle
 * behaviours nudge a few more. Nothing else in the module touches pixels.
 *
 * That split is the point. Swap this file for a Rive board or a 3D head with
 * blendshapes and the emotion engine, the lip-sync engine and the public API
 * are all unchanged — the parameter names are the contract. */
(function (NS) {

  /* ── the parameter contract ──────────────────────────────────────────
     Anything a renderer must understand. Ranges are advisory, not clamped,
     because overshoot from the spring is what makes motion feel alive.      */
  var PARAMS = {
    headTurn:   0,    // -1 left .. +1 right   (yaw, faked in 2.5D)
    headTilt:   0,    // -1 .. +1              (roll)
    headNod:    0,    // -1 up .. +1 down      (pitch)
    lean:       0,    // -1 back .. +1 toward the student
    bounce:     0,    // 0 .. 1                vertical excitement
    breathe:    0,    // 0 .. 1                driven by idle

    browRaise:  0,    // -1 lowered .. +1 raised
    browInner:  0,    // -1 inner-down (focus) .. +1 inner-up (concern)
    browAsym:   0,    // 0 .. 1   one brow higher than the other

    eyeOpen:    1,    // 0 shut .. 1 normal .. 1.35 wide
    eyeSquint:  0,    // 0 .. 1   lower lid rises — the Duchenne smile
    lookX:      0,    // -1 .. +1
    lookY:      0,    // -1 up .. +1 down

    mouthOpen:  0.06, // 0 .. 1
    mouthWidth: 0.5,  // 0 narrow .. 0.5 neutral .. 1 wide
    mouthCurve: 0.12, // -1 frown .. +1 smile
    mouthPurse: 0,    // 0 .. 1   rounded, for O / U
    teeth:      0,    // 0 .. 1

    cheekRaise: 0,    // 0 .. 1
    blush:      0     // 0 .. 1
  };

  NS.PARAMS = PARAMS;
  NS.newParams = function () {
    var p = {};
    for (var k in PARAMS) p[k] = PARAMS[k];
    return p;
  };

  /* ── palette ─────────────────────────────────────────────────────────
     A warm, stylised illustration. Deliberately not photoreal: at this level
     of abstraction the viewer forgives a lot and the uncanny valley never
     opens up.                                                              */
  var C = {
    // skin — light and peachy, lit from the upper left
    skinLit:   '#FFE0CC',
    skin:      '#F8CBB0',
    skinShade: '#EBA98B',
    skinDeep:  '#D98E70',
    blush:     '#F1978F',

    // hair — warm brown with visible strand lighting
    hair:      '#8A4C2C',
    hairDark:  '#5C3220',
    hairLight: '#B87344',
    hairSheen: '#DFA771',
    brow:      '#5B3520',

    // eyes — large, hazel-gold
    sclera:    '#FFFFFF',
    scleraSh:  '#E8DED6',
    iris:      '#9A8235',
    irisDeep:  '#6B5722',
    irisLight: '#C0A64B',
    pupil:     '#2A2118',
    lash:      '#2E2119',

    // round tortoiseshell glasses
    frame:     '#8A4F32',
    frameLit:  '#B0714A',

    lip:       '#E89A93',
    lipDark:   '#CE706A',
    mouthIn:   '#A2565A',
    tongue:    '#C97C7C',
    teeth:     '#FFFDFA',

    // mint collared shirt
    top:       '#B7DFD1',
    topShade:  '#96C6B4',
    topLit:    '#D6EFE6',
    topTrim:   '#CFEBE0',
    button:    '#D9CBA9'
  };
  NS.PALETTE = C;

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  function ellipse(g, x, y, rx, ry, rot) {
    g.beginPath(); g.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), rot || 0, 0, Math.PI * 2);
  }

  /* ── the drawing ─────────────────────────────────────────────────────
     Authored in a fixed 300x340 space and scaled to fit, so every magic
     number below is stable regardless of canvas size.                     */
  var W = 300, H = 340;
  NS.DESIGN = { w: W, h: H };

  NS.draw = function (ctx, p, opts) {
    opts = opts || {};
    var cw = opts.width, ch = opts.height;
    var s = Math.min(cw / W, ch / H);
    ctx.save();
    ctx.clearRect(0, 0, cw, ch);
    ctx.translate((cw - W * s) / 2, (ch - H * s) / 2);
    ctx.scale(s, s);

    var breathe = Math.sin(p.breathe * Math.PI * 2) * 1.2;
    var bounceY = -p.bounce * 7;
    var leanY = p.lean * 3;

    /* ---- body ---------------------------------------------------- */
    ctx.save();
    ctx.translate(0, breathe * 0.6 + bounceY * 0.35 + leanY);
    drawBody(ctx, p);
    ctx.restore();

    /* ---- head ------------------------------------------------------
       Yaw is faked: shift the features, and shift the head silhouette a
       little less, which reads as rotation at this stylisation.          */
    var hx = 150, hy = 143 + breathe + bounceY + p.headNod * 7 + leanY * 1.6;
    ctx.save();
    ctx.translate(hx, hy);
    ctx.rotate(p.headTilt * 0.16);
    ctx.translate(p.headTurn * 5, 0);
    drawHead(ctx, p);
    ctx.restore();

    ctx.restore();
  };

  /* ── body ─────────────────────────────────────────────────────────── */
  function drawBody(ctx, p) {
    var shift = p.headTurn * 2.5;

    // neck — slim, and SHORT. The reference reads as a big head on a small
    // neck; a long one immediately looks wrong.
    var ng = ctx.createLinearGradient(128, 0, 172, 0);
    ng.addColorStop(0, C.skinDeep);
    ng.addColorStop(0.45, C.skinShade);
    ng.addColorStop(1, C.skinDeep);
    ctx.fillStyle = ng;
    ctx.beginPath();
    ctx.moveTo(136 + shift, 208);
    ctx.bezierCurveTo(135, 240, 131, 252, 127 + shift * 0.4, 266);
    ctx.lineTo(173 + shift * 0.4, 266);
    ctx.bezierCurveTo(169, 252, 165, 240, 164 + shift, 208);
    ctx.closePath(); ctx.fill();

    // shoulders — wide, so the crop reads as a bust and not a hill
    var sg = ctx.createLinearGradient(6, 0, 294, 0);
    sg.addColorStop(0, C.topShade);
    sg.addColorStop(0.32, C.top);
    sg.addColorStop(0.6, C.topLit);
    sg.addColorStop(1, C.topShade);
    ctx.fillStyle = sg;
    ctx.beginPath();
    ctx.moveTo(150, 262);
    ctx.bezierCurveTo(190, 263, 226, 274, 250, 296);
    ctx.bezierCurveTo(272, 316, 282, 328, 288, 340);
    ctx.lineTo(12, 340);
    ctx.bezierCurveTo(18, 328, 28, 316, 50, 296);
    ctx.bezierCurveTo(74, 274, 110, 263, 150, 262);
    ctx.closePath(); ctx.fill();

    // collar. The band BEHIND the neck is what makes it read as a shirt
    // collar rather than a coloured hill.
    ctx.fillStyle = C.topShade;
    ctx.beginPath();
    ctx.moveTo(120 + shift * 0.4, 262);
    ctx.quadraticCurveTo(150 + shift * 0.4, 246, 180 + shift * 0.4, 262);
    ctx.quadraticCurveTo(150 + shift * 0.4, 274, 120 + shift * 0.4, 262);
    ctx.closePath(); ctx.fill();

    ctx.fillStyle = C.topLit;
    [-1, 1].forEach(function (sd) {
      ctx.beginPath();
      ctx.moveTo(150 + sd * 22 + shift * 0.4, 258);
      ctx.bezierCurveTo(150 + sd * 52, 262, 150 + sd * 70, 288, 150 + sd * 66, 316);
      ctx.bezierCurveTo(150 + sd * 38, 302, 150 + sd * 14, 294, 150, 302);
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = 'rgba(88,142,124,0.8)'; ctx.lineWidth = 2.2; ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(150 + sd * 22 + shift * 0.4, 258);
      ctx.bezierCurveTo(150 + sd * 52, 262, 150 + sd * 70, 288, 150 + sd * 66, 316);
      ctx.bezierCurveTo(150 + sd * 38, 302, 150 + sd * 14, 294, 150, 302);
      ctx.stroke();
    });

    // placket + buttons
    ctx.strokeStyle = 'rgba(96,150,132,0.6)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(150, 302); ctx.lineTo(150, 340); ctx.stroke();
    ctx.fillStyle = C.button;
    [318, 336].forEach(function (by) {
      ellipse(ctx, 150, by, 4.2, 4.2); ctx.fill();
      ctx.strokeStyle = 'rgba(120,100,64,0.5)'; ctx.lineWidth = 1;
      ellipse(ctx, 150, by, 4.2, 4.2); ctx.stroke();
      ctx.fillStyle = C.button;
    });

    // shadow the head casts onto the chest
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(150, 262);
    ctx.bezierCurveTo(190, 263, 226, 274, 250, 296);
    ctx.bezierCurveTo(272, 316, 282, 328, 288, 340);
    ctx.lineTo(12, 340);
    ctx.bezierCurveTo(18, 328, 28, 316, 50, 296);
    ctx.bezierCurveTo(74, 274, 110, 263, 150, 262);
    ctx.closePath(); ctx.clip();
    var cs = ctx.createRadialGradient(150, 246, 12, 150, 246, 86);
    cs.addColorStop(0, 'rgba(80,116,104,0.34)');
    cs.addColorStop(1, 'rgba(80,116,104,0)');
    ctx.fillStyle = cs; ctx.fillRect(6, 244, 288, 100);
    ctx.restore();
  }

  /* ── head ──────────────────────────────────────────────────────────
     Origin is the centre of the face. The look is soft-3D: every mass gets
     a gradient rather than a flat fill, and the light is consistently from
     the upper left.                                                       */
  function drawHead(ctx, p) {
    var t = p.headTurn;
    var fx = t * 10;

    // ── hair behind: the back mass and the low side bun ──
    ctx.fillStyle = C.hairDark;
    ctx.beginPath();
    ctx.moveTo(-88 + t * 2, -12);
    ctx.bezierCurveTo(-100, -90, -56, -124, 0, -124);
    ctx.bezierCurveTo(56, -124, 100, -90, 88 + t * 2, -12);
    ctx.bezierCurveTo(94, 26, 86, 54, 74, 68);
    ctx.bezierCurveTo(28, 84, -28, 84, -74, 68);
    ctx.bezierCurveTo(-86, 54, -94, 26, -88 + t * 2, -12);
    ctx.closePath(); ctx.fill();

    // braided bun, low on her right (viewer's left)
    ctx.save();
    ctx.translate(-84 + t * 4, 28);
    var bg = ctx.createRadialGradient(-4, -6, 2, 0, 0, 20);
    bg.addColorStop(0, C.hairLight);
    bg.addColorStop(1, C.hairDark);
    ctx.fillStyle = bg;
    ellipse(ctx, 0, 0, 20, 23, -0.28); ctx.fill();
    ctx.strokeStyle = 'rgba(58,38,28,0.55)'; ctx.lineWidth = 1.6;
    [-9, 0, 9].forEach(function (o) {
      ctx.beginPath();
      ctx.moveTo(-15, o - 4); ctx.quadraticCurveTo(0, o + 5, 15, o - 4);
      ctx.stroke();
    });
    ctx.restore();

    // ── ears ──
    ctx.fillStyle = C.skinShade;
    ellipse(ctx, -70 + fx * 0.4, 2, 8.5, 13); ctx.fill();
    ellipse(ctx, 70 + fx * 0.4, 2, 8.5, 13); ctx.fill();

    // ── face: a soft rounded mass, lit from the upper left ──
    ctx.beginPath();
    ctx.moveTo(-70 + fx * 0.3, -22);
    ctx.bezierCurveTo(-70, -80, -41, -104, 0 + fx * 0.3, -104);
    ctx.bezierCurveTo(41, -104, 70, -80, 70 + fx * 0.3, -22);
    ctx.bezierCurveTo(70, 26, 53, 62, 0 + fx * 0.5, 76);
    ctx.bezierCurveTo(-53, 62, -70, 26, -70 + fx * 0.3, -22);
    ctx.closePath();
    var fg = ctx.createRadialGradient(-28 + fx, -46, 16, 4 + fx, 6, 108);
    fg.addColorStop(0, C.skinLit);
    fg.addColorStop(0.5, C.skin);
    fg.addColorStop(1, C.skinShade);
    ctx.fillStyle = fg; ctx.fill();

    ctx.save();
    ctx.clip();

    // form shadow down the away side
    var sgn = t >= 0 ? -1 : 1;
    var sx = ctx.createLinearGradient(sgn * 26, 0, sgn * 82, 0);
    sx.addColorStop(0, 'rgba(196,124,96,0)');
    sx.addColorStop(1, 'rgba(196,124,96,0.24)');
    ctx.fillStyle = sx; ctx.fillRect(Math.min(sgn * 22, sgn * 78), -110, 78, 196);

    // under-jaw shadow
    var jg = ctx.createLinearGradient(0, 36, 0, 78);
    jg.addColorStop(0, 'rgba(196,124,96,0)');
    jg.addColorStop(1, 'rgba(196,124,96,0.22)');
    ctx.fillStyle = jg; ctx.fillRect(-72, 36, 144, 44);

    // shadow the fringe casts across the forehead
    var hg = ctx.createLinearGradient(0, -104, 0, -52);
    hg.addColorStop(0, 'rgba(140,86,62,0.32)');
    hg.addColorStop(1, 'rgba(140,86,62,0)');
    ctx.fillStyle = hg; ctx.fillRect(-72, -106, 144, 56);

    // blush — soft radial, always slightly present
    var bl = 0.5 + clamp(p.blush, 0, 1) * 0.5;
    [-1, 1].forEach(function (sd) {
      var r = ctx.createRadialGradient(sd * 40 + fx, 22, 1, sd * 40 + fx, 22, 25);
      r.addColorStop(0, 'rgba(244,146,138,' + (bl * 0.62).toFixed(3) + ')');
      r.addColorStop(1, 'rgba(244,146,138,0)');
      ctx.fillStyle = r;
      ctx.fillRect(sd * 40 + fx - 27, 0, 54, 48);
    });
    ctx.restore();

    drawBrows(ctx, p, fx);
    drawEyes(ctx, p, fx);
    drawNose(ctx, p, fx);
    drawMouth(ctx, p, fx);
    drawGlasses(ctx, p, fx);

    // ── hair in front: centre part, swept back over each side ──
    function sweep(side) {
      ctx.beginPath();
      ctx.moveTo(0 + t * 3, -118);
      ctx.bezierCurveTo(side * 40, -122, side * 78, -100, side * 86 + t * 3, -44);
      ctx.bezierCurveTo(side * 92, -14, side * 90, 12, side * 84, 30);
      ctx.bezierCurveTo(side * 77, -12, side * 63, -46, side * 38 + t * 4, -60);
      ctx.bezierCurveTo(side * 20, -72, side * 7, -88, 0 + t * 3, -118);
      ctx.closePath();
      var g = ctx.createLinearGradient(side * 9, -118, side * 88, 30);
      g.addColorStop(0, C.hairDark);
      g.addColorStop(0.34, C.hairLight);
      g.addColorStop(0.62, C.hair);
      g.addColorStop(1, C.hairDark);
      ctx.fillStyle = g; ctx.fill();

      // strand sheen following the sweep
      ctx.strokeStyle = 'rgba(223,167,113,0.62)'; ctx.lineWidth = 2.4; ctx.lineCap = 'round';
      [0, 1, 2].forEach(function (i) {
        ctx.beginPath();
        ctx.moveTo(side * (9 + i * 5) + t * 3, -111 + i * 6);
        ctx.bezierCurveTo(side * (44 + i * 6), -109 + i * 5, side * (72 + i * 5), -89 + i * 6,
                          side * (80 + i * 2) + t * 3, -49 + i * 9);
        ctx.stroke();
      });
    }
    sweep(-1); sweep(1);

    // the parting itself
    ctx.strokeStyle = C.hairDark; ctx.lineWidth = 2.4; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(0 + t * 3, -118); ctx.quadraticCurveTo(-2 + t * 3, -104, -1 + t * 3, -92);
    ctx.stroke();
  }

  /* ── round tortoiseshell glasses ───────────────────────────────────
     Drawn last so the frame sits over the eyes, with a highlight on each
     lens to sell the glass.                                              */
  function drawGlasses(ctx, p, fx) {
    var y = -10, r = 32;
    var lx = -32 + fx, rx = 32 + fx;

    // lens glass — barely there. A stronger fill greys out the eyes and turns
    // the lashes into scratches, which is what it did before this was dialled back.
    [-1, 1].forEach(function (sd) {
      var cx = sd < 0 ? lx : rx;
      var g = ctx.createLinearGradient(cx - r, y - r, cx + r * 0.4, y + r);
      g.addColorStop(0, 'rgba(255,255,255,0.16)');
      g.addColorStop(0.55, 'rgba(255,255,255,0.02)');
      g.addColorStop(1, 'rgba(210,230,240,0.05)');
      ctx.fillStyle = g;
      ellipse(ctx, cx, y, r - 2, r - 2); ctx.fill();
    });

    ctx.lineWidth = 4.6; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    var fgr = ctx.createLinearGradient(lx - r, y - r, rx + r, y + r);
    fgr.addColorStop(0, C.frameLit);
    fgr.addColorStop(0.5, C.frame);
    fgr.addColorStop(1, C.frameLit);
    ctx.strokeStyle = fgr;

    ellipse(ctx, lx, y, r, r); ctx.stroke();
    ellipse(ctx, rx, y, r, r); ctx.stroke();

    // bridge
    ctx.beginPath();
    ctx.moveTo(lx + r - 1, y - 5);
    ctx.quadraticCurveTo(fx, y - 12, rx - r + 1, y - 5);
    ctx.stroke();

    // temples out to the ears
    ctx.lineWidth = 3.8;
    ctx.beginPath(); ctx.moveTo(lx - r + 2, y - 6); ctx.lineTo(-68 + fx * 0.5, y - 3); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(rx + r - 2, y - 6); ctx.lineTo(68 + fx * 0.5, y - 3); ctx.stroke();

    // a soft glint high on each lens — anything stronger reads as a scratch
    ctx.lineCap = 'round';
    [-1, 1].forEach(function (sd) {
      var cx = sd < 0 ? lx : rx;
      ctx.strokeStyle = 'rgba(255,255,255,0.34)'; ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.arc(cx, y, r - 9, Math.PI * 1.12, Math.PI * 1.36);
      ctx.stroke();
    });
  }

  /* ── brows: thick, dark, sitting above the frames ──────────────────── */
  function drawBrows(ctx, p, fx) {
    var raise = p.browRaise * 9;
    var inner = p.browInner * 8;

    function brow(side, extra) {
      var x = side * 32 + fx;
      var y = -50 - raise - extra;
      ctx.fillStyle = C.brow;
      ctx.beginPath();
      ctx.moveTo(x - side * 23, y - inner + 3);
      ctx.quadraticCurveTo(x - side * 5, y - 9.5 - Math.abs(inner) * 0.1, x + side * 21, y + 3.5 + inner * 0.4);
      ctx.quadraticCurveTo(x - side * 5, y - 3 - Math.abs(inner) * 0.1, x - side * 23, y - inner + 8.5);
      ctx.closePath(); ctx.fill();
    }
    brow(-1, 0);
    brow(1, p.browAsym * 9);
  }

  /* ── eyes: large and round, hazel-gold ─────────────────────────────── */
  function drawEyes(ctx, p, fx) {
    var open = clamp(p.eyeOpen, 0, 1.4);
    var squint = clamp(p.eyeSquint, 0, 1);

    function eye(side) {
      var x = side * 32 + fx, y = -10;
      var narrow = (side === Math.sign(p.headTurn)) ? 0 : Math.abs(p.headTurn) * 2.5;
      var rx = 23 - narrow;
      var ryTop = 18 * open;
      var ryBot = 17 * open * (1 - squint * 0.62);

      if (ryTop < 1.2) {                        // shut: a lash curve
        ctx.strokeStyle = C.lash; ctx.lineWidth = 3.2; ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x - rx, y - 1); ctx.quadraticCurveTo(x, y + 7, x + rx, y - 1);
        ctx.stroke();
        return;
      }

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x - rx, y);
      ctx.quadraticCurveTo(x, y - ryTop * 1.6, x + rx, y);
      ctx.quadraticCurveTo(x, y + ryBot * 1.6, x - rx, y);
      ctx.closePath();
      var sg = ctx.createLinearGradient(0, y - ryTop, 0, y + ryBot);
      sg.addColorStop(0, C.scleraSh);
      sg.addColorStop(0.42, C.sclera);
      sg.addColorStop(1, '#F3ECE6');
      ctx.fillStyle = sg; ctx.fill();
      ctx.clip();

      var ix = x + p.lookX * 6, iy = y + p.lookY * 5 + 1;
      var ig = ctx.createRadialGradient(ix - 2, iy - 3, 1.5, ix, iy, 12.5);
      ig.addColorStop(0, C.irisLight);
      ig.addColorStop(0.55, C.iris);
      ig.addColorStop(1, C.irisDeep);
      ellipse(ctx, ix, iy, 12.5, 12.5); ctx.fillStyle = ig; ctx.fill();
      ctx.strokeStyle = 'rgba(58,44,16,0.6)'; ctx.lineWidth = 1.6;
      ellipse(ctx, ix, iy, 12.5, 12.5); ctx.stroke();
      ellipse(ctx, ix, iy, 5.4, 5.4); ctx.fillStyle = C.pupil; ctx.fill();
      ellipse(ctx, ix - 4, iy - 4.6, 3.6, 3, -0.5); ctx.fillStyle = 'rgba(255,255,255,.95)'; ctx.fill();
      ellipse(ctx, ix + 4.4, iy + 3.6, 1.8, 1.5); ctx.fillStyle = 'rgba(255,255,255,.6)'; ctx.fill();

      var us = ctx.createLinearGradient(0, y - ryTop * 1.5, 0, y);
      us.addColorStop(0, 'rgba(120,90,70,0.34)');
      us.addColorStop(1, 'rgba(120,90,70,0)');
      ctx.fillStyle = us; ctx.fillRect(x - rx, y - ryTop * 1.6, rx * 2, ryTop * 1.6);
      ctx.restore();

      // upper lash line, thick, with lashes at the outer corner
      ctx.strokeStyle = C.lash; ctx.lineWidth = 3.6; ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x - rx, y); ctx.quadraticCurveTo(x, y - ryTop * 1.68, x + rx, y);
      ctx.stroke();
      ctx.strokeStyle = C.lash; ctx.lineWidth = 2.8;
      [0, 1, 2].forEach(function (i) {
        var f = 0.6 + i * 0.14;
        var px0 = x + side * rx * f;
        var py0 = y - ryTop * (1.02 - Math.abs(f - 0.75) * 0.9);
        ctx.beginPath();
        ctx.moveTo(px0, py0);
        ctx.quadraticCurveTo(px0 + side * 2.6, py0 - 3.4, px0 + side * 4.2, py0 - 5.4);
        ctx.stroke();
      });

    }
    eye(-1); eye(1);
  }

  /* ── a small button nose ───────────────────────────────────────────── */
  function drawNose(ctx, p, fx) {
    var x = fx * 1.15, y = 24;
    var g = ctx.createRadialGradient(x - 3, y - 4, 1, x, y, 12);
    g.addColorStop(0, 'rgba(255,224,204,0.9)');
    g.addColorStop(0.55, 'rgba(235,169,139,0.45)');
    g.addColorStop(1, 'rgba(235,169,139,0)');
    ctx.fillStyle = g;
    ellipse(ctx, x, y, 12.5, 10); ctx.fill();
    ctx.strokeStyle = 'rgba(210,140,112,0.55)'; ctx.lineWidth = 2.4; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x - 6.5, y + 3); ctx.quadraticCurveTo(x, y + 7.5, x + 6.5, y + 3);
    ctx.stroke();
  }

  /* ── mouth ─────────────────────────────────────────────────────────
     Same three parameters as before — how open, how wide, how curved,
     plus purse. Every viseme and every smile is a point in that space.   */
  function drawMouth(ctx, p, fx) {
    var open = clamp(p.mouthOpen, 0, 1);
    var purse = clamp(p.mouthPurse, 0, 1);
    var w = lerp(17, 36, clamp(p.mouthWidth, 0, 1)) * (1 - purse * 0.45);
    var curve = clamp(p.mouthCurve, -1, 1);
    var cy = 48;
    var x = fx * 1.3;

    var h = open * 24 * (1 + purse * 0.2);
    var cornerY = cy - curve * 10;

    if (h < 1.8) {                              // closed
      ctx.strokeStyle = C.lipDark; ctx.lineWidth = 3.6; ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x - w, cornerY);
      ctx.quadraticCurveTo(x, cy + curve * 8 + 4, x + w, cornerY);
      ctx.stroke();
      // lower lip, given a little volume
      var lg = ctx.createLinearGradient(0, cornerY, 0, cornerY + 14);
      lg.addColorStop(0, C.lip);
      lg.addColorStop(1, 'rgba(232,154,147,0)');
      ctx.fillStyle = lg;
      ctx.beginPath();
      ctx.moveTo(x - w * 0.85, cornerY + 1);
      ctx.quadraticCurveTo(x, cy + curve * 8 + 12, x + w * 0.85, cornerY + 1);
      ctx.quadraticCurveTo(x, cy + curve * 8 + 4, x - w * 0.85, cornerY + 1);
      ctx.closePath(); ctx.fill();
      if (curve > 0.3) smileCreases(ctx, x, w, cornerY);
      return;
    }

    function mouthPath() {
      ctx.beginPath();
      ctx.moveTo(x - w, cornerY);
      ctx.quadraticCurveTo(x, cy - h * 0.8 + curve * 4, x + w, cornerY);
      ctx.quadraticCurveTo(x, cy + h * 1.1 + curve * 5, x - w, cornerY);
      ctx.closePath();
    }

    ctx.fillStyle = C.mouthIn; mouthPath(); ctx.fill();

    if (p.teeth > 0.05 && h > 4) {
      ctx.save(); mouthPath(); ctx.clip();
      ctx.fillStyle = C.teeth;
      ctx.fillRect(x - w, cornerY - h * 0.85, w * 2, h * 0.5 + p.teeth * 6);
      ctx.restore();
    }
    if (h > 11) {
      ctx.save(); mouthPath(); ctx.clip();
      ctx.fillStyle = C.tongue;
      ellipse(ctx, x, cy + h * 0.9, w * 0.6, h * 0.45); ctx.fill();
      ctx.restore();
    }

    ctx.strokeStyle = C.lip; ctx.lineWidth = 3.6; ctx.lineJoin = 'round';
    mouthPath(); ctx.stroke();
    if (curve > 0.3) smileCreases(ctx, x, w, cornerY);
  }

  /* A dimple, not a fold. The old version drew a long nasolabial crease, which
     is one of the strongest "older face" cues there is. */
  function smileCreases(ctx, x, w, cornerY) {
    ctx.fillStyle = 'rgba(214,150,124,0.17)';
    [-1, 1].forEach(function (sd) {
      ellipse(ctx, x + sd * (w + 3.5), cornerY - 1.5, 2, 2.6); ctx.fill();
    });
  }

  NS.lerp = lerp;
  NS.clamp = clamp;

})(typeof window !== 'undefined' ? (window.Nityam = window.Nityam || {}) : (module.exports = {}));
