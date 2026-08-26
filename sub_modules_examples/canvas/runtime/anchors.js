/* The anchor registry — the index that turns pixels back into meaning.
 *
 * Every block, as it renders, registers the regions of itself that MEAN
 * something: a phrase, an equation term, an SVG group, a hotspot in an image.
 * A gesture is then resolved by intersecting it with this index.
 *
 * Rects are measured lazily and cached, because measuring is the expensive part
 * and the layout only moves on resize. */
(function (NS) {

  NS.createAnchorRegistry = function () {
    var byId = {};        // anchorId -> record
    var order = [];       // registration order, for stable output
    var dirty = true;

    function register(rec) {
      if (byId[rec.id]) {
        console.warn('[nityam:canvas] duplicate anchor id: ' + rec.id);
        return byId[rec.id];
      }
      byId[rec.id] = rec;
      order.push(rec.id);
      dirty = true;
      return rec;
    }

    /* Measure every anchor's box in PAGE coordinates, not viewport coordinates,
       so a scroll does not invalidate anything. */
    function measure() {
      order.forEach(function (id) {
        var rec = byId[id];
        var el = rec.el;
        if (!el || !rec.pageEl) { rec.rect = null; return; }

        var pb = rec.pageEl.getBoundingClientRect();
        var boxes = [];

        if (rec.kind === 'image_region') {
          /* fractional coords against the rendered image */
          var ib = el.getBoundingClientRect();
          var f = rec.frac;
          boxes.push({
            x: ib.left - pb.left + f[0] * ib.width,
            y: ib.top - pb.top + f[1] * ib.height,
            w: f[2] * ib.width,
            h: f[3] * ib.height
          });
        } else if (rec.kind === 'text_span') {
          /* a phrase can wrap across lines — keep every client rect */
          var rects = el.getClientRects();
          for (var i = 0; i < rects.length; i++) {
            var r = rects[i];
            if (r.width < 1 || r.height < 1) continue;
            boxes.push({ x: r.left - pb.left, y: r.top - pb.top, w: r.width, h: r.height });
          }
        } else {
          var b = el.getBoundingClientRect();
          boxes.push({ x: b.left - pb.left, y: b.top - pb.top, w: b.width, h: b.height });
        }

        rec.boxes = boxes;
        rec.rect = boxes.length ? union(boxes) : null;
      });
      dirty = false;
    }

    function union(boxes) {
      var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      boxes.forEach(function (b) {
        x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
        x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
      });
      return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }

    return {
      register: register,
      invalidate: function () { dirty = true; },
      get: function (id) { return byId[id]; },
      all: function () { return order.map(function (id) { return byId[id]; }); },

      /* Anchors on one page, measured. The only entry point the resolver uses. */
      onPage: function (pageNo) {
        if (dirty) measure();
        return order.map(function (id) { return byId[id]; })
                    .filter(function (r) { return r.page === pageNo && r.boxes && r.boxes.length; });
      },

      /* Public shape of an anchor once it leaves the registry. */
      describe: function (rec, coverage) {
        var out = {
          anchor: rec.id,
          kind: rec.kind,
          text: rec.text || null,
          block: rec.blockId,
          coverage: Math.round(coverage * 100) / 100
        };
        if (rec.concept) out.concept = rec.concept;
        if (rec.note) out.note = rec.note;
        if (rec.misconception) out.misconception = rec.misconception;
        return out;
      }
    };
  };

  NS.union = function (boxes) {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    boxes.forEach(function (b) {
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
      x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
    });
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  };

})(typeof window !== 'undefined' ? (window.Nityam = window.Nityam || {}) : (module.exports = {}));
