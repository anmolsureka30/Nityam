/* The grounding resolver: a gesture becomes a ContextPacket.
 *
 * This is the point of the whole sub-module. A bounding box at (340,210) is
 * useless to a tutor; "you circled (u sinθ)², the vertical component squared"
 * is a conversation.
 *
 * Three tiers, tried in order:
 *   1  text selection  → exact DOM Range, no geometry involved
 *   2  geometry        → stroke/polygon vs the anchor rect index, scored by coverage
 *   3  crop            → for image blocks, an actual pixel crop for a vision call
 *
 * Coverage becomes confidence. A sloppy circle across two terms should degrade
 * into "probably this, possibly that" rather than one confident wrong answer,
 * so anchors below RESOLVE_FLOOR are reported as `nearby` instead of `resolved`. */
(function (NS) {

  var RESOLVE_FLOOR = 0.35;    // below this, an anchor is context, not the referent
  var NEARBY_FLOOR  = 0.05;    // below this, ignore entirely

  /* ── geometry ─────────────────────────────────────────────────────── */

  function overlap1d(a0, a1, b0, b1) {
    return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));
  }

  /* A highlighter swipe is a BAND along a line, so plain area-intersection
     scores it badly: swiping across a tall stacked fraction covers maybe a
     quarter of its area and would fall below the resolve floor, even though
     the student unambiguously meant that term.
     Score a marker by how much of the anchor's WIDTH was swept, gated on the
     band actually meeting the anchor vertically. */
  function markerCoverage(box, band) {
    var vo = overlap1d(box.y, box.y + box.h, band.y, band.y + band.h);
    if (vo <= 0 || box.w <= 0) return 0;
    var vFactor = Math.min(1, vo / Math.max(1, Math.min(band.h, box.h)));
    var ho = overlap1d(box.x, box.x + box.w, band.x, band.x + band.w);
    return (ho / box.w) * vFactor;
  }
  NS.markerCoverage = markerCoverage;

  function pointInPolygon(px, py, poly) {
    var inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }

  /* Fraction of `box` covered by a closed polygon, by sampling. Exact clipping
     is not worth it here: a 6x6 grid separates "circled it" from "clipped its
     corner" perfectly well, and the number only has to rank anchors. */
  function polygonCoverage(box, poly) {
    if (box.w <= 0 || box.h <= 0) return 0;
    var N = 6, hit = 0;
    for (var i = 0; i < N; i++) {
      for (var j = 0; j < N; j++) {
        var px = box.x + (i + 0.5) / N * box.w;
        var py = box.y + (j + 0.5) / N * box.h;
        if (pointInPolygon(px, py, poly)) hit++;
      }
    }
    return hit / (N * N);
  }
  NS.polygonCoverage = polygonCoverage;

  function polyBBox(poly) {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    poly.forEach(function (p) {
      x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]);
      x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]);
    });
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
  NS.polyBBox = polyBBox;

  /* How much of an anchor did this gesture cover?
     marker  → band intersection, because a highlight is a swipe not an enclosure
     circle  → polygon containment
     lasso   → polygon containment */
  function scoreAnchor(rec, gesture) {
    var best = 0, total = 0, covered = 0;
    rec.boxes.forEach(function (box) {
      var area = box.w * box.h;
      if (area <= 0) return;
      var c;
      if (gesture.type === 'marker') {
        c = markerCoverage(box, gesture.bbox);
      } else {
        c = polygonCoverage(box, gesture.points);
      }
      total += area;
      covered += c * area;
      best = Math.max(best, c);
    });
    /* area-weighted across a wrapped phrase, but a single strongly-hit line
       should still count — take the more generous of the two */
    var weighted = total > 0 ? covered / total : 0;
    return Math.max(weighted, best * 0.85);
  }
  NS.scoreAnchor = scoreAnchor;

  /* ── tier 3: crop ─────────────────────────────────────────────────── */

  /* Only image blocks can be cropped for real. Text and diagram blocks would
     need a DOM rasteriser, which this proof of concept deliberately does not
     add — the packet says crop:null and reports the block instead. */
  function cropImage(imgEl, pageEl, bbox) {
    try {
      var ib = imgEl.getBoundingClientRect(), pb = pageEl.getBoundingClientRect();
      var ix = ib.left - pb.left, iy = ib.top - pb.top;

      var sx = (bbox.x - ix) / ib.width, sy = (bbox.y - iy) / ib.height;
      var sw = bbox.w / ib.width,        sh = bbox.h / ib.height;
      sx = Math.max(0, Math.min(1, sx)); sy = Math.max(0, Math.min(1, sy));
      sw = Math.max(0.01, Math.min(1 - sx, sw)); sh = Math.max(0.01, Math.min(1 - sy, sh));

      var nw = imgEl.naturalWidth || ib.width, nh = imgEl.naturalHeight || ib.height;
      var c = document.createElement('canvas');
      c.width = Math.round(sw * nw); c.height = Math.round(sh * nh);
      if (!c.width || !c.height) return null;
      c.getContext('2d').drawImage(imgEl, sx * nw, sy * nh, sw * nw, sh * nh, 0, 0, c.width, c.height);
      return c.toDataURL('image/png');
    } catch (e) {
      console.warn('[nityam:canvas] crop failed:', e.message);
      return null;
    }
  }

  /* ── the resolver ─────────────────────────────────────────────────── */

  /* gesture = { type:'marker'|'circle'|'lasso'|'selection', page, points[], bbox,
                 selectedAnchors[] (selection only), selectedText }            */
  NS.resolveGesture = function (gesture, registry, ctx) {
    ctx = ctx || {};
    var packet = {
      gesture: gesture.type,
      page: gesture.page,
      utterance: gesture.utterance || null,
      resolved: [],
      nearby: [],
      block: null,
      bbox: gesture.bbox ? [
        Math.round(gesture.bbox.x), Math.round(gesture.bbox.y),
        Math.round(gesture.bbox.w), Math.round(gesture.bbox.h)
      ] : null,
      confidence: 0,
      crop: null,
      tier: null
    };

    /* ── tier 1: a real text selection is exact, skip the geometry ── */
    if (gesture.type === 'selection') {
      packet.tier = 'selection';
      packet.selected_text = gesture.selectedText || null;
      (gesture.selectedAnchors || []).forEach(function (id) {
        var rec = registry.get(id);
        if (rec) packet.resolved.push(registry.describe(rec, 1));
      });
      packet.confidence = packet.resolved.length ? 1 : 0;
      if (packet.resolved.length) packet.block = packet.resolved[0].block;
      return packet;
    }

    /* ── tier 2: geometry against the anchor index ── */
    packet.tier = 'geometry';
    var scored = registry.onPage(gesture.page).map(function (rec) {
      return { rec: rec, c: scoreAnchor(rec, gesture) };
    }).filter(function (s) {
      return s.c >= NEARBY_FLOOR;
    }).sort(function (a, b) { return b.c - a.c; });

    scored.forEach(function (s) {
      var d = registry.describe(s.rec, s.c);
      if (s.c >= RESOLVE_FLOOR) packet.resolved.push(d);
      else packet.nearby.push(d);
    });

    packet.confidence = packet.resolved.length ? packet.resolved[0].coverage : 0;
    packet.block = packet.resolved.length ? packet.resolved[0].block
                 : (packet.nearby.length ? packet.nearby[0].block : null);

    /* ── tier 3: crop, when the gesture landed on an image ── */
    var blockId = packet.block || (ctx.blockAt ? ctx.blockAt(gesture) : null);
    if (blockId && ctx.imageOf) {
      var imgEl = ctx.imageOf(blockId);
      if (imgEl && ctx.pageEl) {
        packet.crop = cropImage(imgEl, ctx.pageEl, gesture.bbox);
        if (packet.crop) packet.tier = 'geometry+crop';
      }
    }
    if (!packet.block && blockId) packet.block = blockId;

    return packet;
  };

  NS.RESOLVE_FLOOR = RESOLVE_FLOOR;
  NS.NEARBY_FLOOR = NEARBY_FLOOR;

})(typeof window !== 'undefined' ? (window.Nityam = window.Nityam || {}) : (module.exports = {}));
