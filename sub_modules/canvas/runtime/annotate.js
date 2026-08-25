/* The annotation layer: marker, circle, lasso — drawn on one SVG per page.
 *
 * Deliberately small. Three tools, an undo stack, and serialisation. No pen
 * pressure, no shape recognition, no object dragging: on a desktop with a
 * mouse, highlight / circle / type is the whole vocabulary a student needs to
 * point at something and ask about it.
 *
 * Strokes live in PAGE coordinates so they survive scrolling and reflow of the
 * surrounding chrome. */
(function (NS) {

  var SVGNS = 'http://www.w3.org/2000/svg';
  var SIMPLIFY_PX = 2.4;      // drop points closer than this; keeps paths light
  var CLOSE_PX = 44;          // circle auto-closes if the ends come back this near

  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  NS.createAnnotator = function (opts) {
    var tool = 'select';
    var strokes = [];           // {id, page, tool, points, colour}
    var undone = [];
    var drawing = null;
    var seq = 0;

    /* ── drawing a stroke into a page's overlay ──────────────────────── */

    function pointsAttr(pts) {
      return pts.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
    }

    function draw(stroke, overlay) {
      var g = svgEl('g', { 'class': 'stroke stroke-' + stroke.tool, 'data-stroke': stroke.id });
      if (stroke.tool === 'marker') {
        g.appendChild(svgEl('polyline', {
          points: pointsAttr(stroke.points), fill: 'none',
          'stroke-width': 17, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
        }));
      } else {
        g.appendChild(svgEl('polygon', { points: pointsAttr(stroke.points), fill: 'none' }));
      }
      overlay.appendChild(g);
      stroke.el = g;
      return g;
    }

    function redrawPage(pageNo, overlay) {
      while (overlay.firstChild) overlay.removeChild(overlay.firstChild);
      strokes.filter(function (s) { return s.page === pageNo; })
             .forEach(function (s) { draw(s, overlay); });
    }

    /* ── pointer handling ────────────────────────────────────────────── */

    function attach(pageEl, overlay, pageNo) {
      overlay.addEventListener('pointerdown', function (e) {
        if (tool === 'select') return;
        /* let the student use the artifact and the textarea normally */
        if (e.target.closest && e.target.closest('.blk-artifact, .work-input')) return;
        e.preventDefault();
        try { overlay.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ }

        var pb = pageEl.getBoundingClientRect();
        drawing = {
          id: 'st' + (++seq), page: pageNo, tool: tool,
          points: [[e.clientX - pb.left, e.clientY - pb.top]]
        };
        draw(drawing, overlay);
      });

      overlay.addEventListener('pointermove', function (e) {
        if (!drawing || drawing.page !== pageNo) return;
        var pb = pageEl.getBoundingClientRect();
        var x = e.clientX - pb.left, y = e.clientY - pb.top;
        var last = drawing.points[drawing.points.length - 1];
        if (Math.hypot(x - last[0], y - last[1]) < SIMPLIFY_PX) return;
        drawing.points.push([x, y]);
        var shape = drawing.el.firstChild;
        shape.setAttribute('points', pointsAttr(drawing.points));
      });

      function finish(e) {
        if (!drawing || drawing.page !== pageNo) return;
        var s = drawing;
        drawing = null;
        try { overlay.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }

        if (s.points.length < 3) {                 // a click, not a gesture
          if (s.el && s.el.parentNode) s.el.parentNode.removeChild(s.el);
          return;
        }
        /* a circle whose ends come back near the start is treated as closed */
        if (s.tool !== 'marker') {
          var a = s.points[0], b = s.points[s.points.length - 1];
          if (Math.hypot(b[0] - a[0], b[1] - a[1]) < CLOSE_PX) s.closed = true;
        }
        strokes.push(s);
        undone.length = 0;
        if (opts.onStroke) opts.onStroke(s, pageEl);
      }

      overlay.addEventListener('pointerup', finish);
      overlay.addEventListener('pointercancel', finish);
    }

    /* ── selection (tier 1) ──────────────────────────────────────────── */

    function anchorsInSelection(sel, pageEl) {
      if (!sel || sel.isCollapsed) return null;
      var range = sel.getRangeAt(0);
      if (!pageEl.contains(range.commonAncestorContainer)) return null;

      var hits = [];
      var spans = pageEl.querySelectorAll('[data-anchor]');
      for (var i = 0; i < spans.length; i++) {
        if (sel.containsNode ? sel.containsNode(spans[i], true)
                             : range.intersectsNode(spans[i])) {
          hits.push(spans[i].dataset.anchor);
        }
      }
      return { text: sel.toString().trim(), anchors: hits };
    }

    return {
      setTool: function (t) { tool = t; },
      getTool: function () { return tool; },
      attach: attach,
      redrawPage: redrawPage,
      anchorsInSelection: anchorsInSelection,

      strokes: function () { return strokes.slice(); },
      strokesOn: function (p) { return strokes.filter(function (s) { return s.page === p; }); },

      undo: function () {
        var s = strokes.pop();
        if (!s) return null;
        undone.push(s);
        if (s.el && s.el.parentNode) s.el.parentNode.removeChild(s.el);
        return s;
      },
      redo: function (overlayFor) {
        var s = undone.pop();
        if (!s) return null;
        strokes.push(s);
        var ov = overlayFor(s.page);
        if (ov) draw(s, ov);
        return s;
      },
      clearPage: function (pageNo, overlay) {
        strokes = strokes.filter(function (s) { return s.page !== pageNo; });
        while (overlay.firstChild) overlay.removeChild(overlay.firstChild);
      },

      /* Serialise without the DOM nodes, so a notebook survives a reload. */
      serialise: function () {
        return strokes.map(function (s) {
          return { id: s.id, page: s.page, tool: s.tool, closed: !!s.closed,
                   points: s.points.map(function (p) { return [Math.round(p[0]), Math.round(p[1])]; }) };
        });
      },
      restore: function (list) {
        strokes = (list || []).map(function (s) { return Object.assign({}, s); });
        strokes.forEach(function (s) {
          var n = parseInt(String(s.id).replace(/\D/g, ''), 10);
          if (n > seq) seq = n;
        });
      }
    };
  };

})(window.Nityam = window.Nityam || {});
