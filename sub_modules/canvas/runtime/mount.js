/* mountCanvas(doc, container, options) -> handle
 *
 * The single entry point, mirroring mountArtifact in the artifact_generator.
 * In the real product:
 *
 *     const nb = Nityam.mountCanvas(canvasDoc, ref.current, {
 *       artifacts, themes,
 *       onGesture: packet => agent.ask(packet),   // <- the whole interface
 *     });
 *     nb.pointAt('t_frac');                        // <- and the tutor points back
 *
 * Everything the tutor needs is on the returned handle. Nothing drives it in
 * this proof of concept; the dev panel in the shell stands in for the agent. */
(function (NS) {

  var STORAGE_KEY = 'nityam.canvas.';

  NS.mountCanvas = function (doc, container, opts) {
    opts = opts || {};
    container.innerHTML = '';
    container.classList.add('nb-root');

    var reg = NS.createAnchorRegistry();
    var artifactHandles = [];
    var images = {};
    var lastPacket = null;

    /* ── surface ──────────────────────────────────────────────────────── */
    var pager = NS.createPager(doc, container, {
      onPageChange: function (n) { if (opts.onPageChange) opts.onPageChange(n); }
    });

    var annot = NS.createAnnotator({
      onStroke: function (stroke, pageEl) { onGesture(strokeToGesture(stroke), pageEl); }
    });

    /* ── content ──────────────────────────────────────────────────────── */
    doc.pages.forEach(function (p) {
      var page = pager.page(p.page);
      var meta = {
        page: p.page, pageEl: page.pageEl, images: images,
        artifacts: opts.artifacts || {}, themes: opts.themes || {},
        artifactCSS: opts.artifactCSS || '',
        artifactHandles: artifactHandles,
        onArtifactEvidence: opts.onArtifactEvidence,
        onRelayout: relayout
      };
      p.blocks.forEach(function (b) { NS.renderBlock(b, page.bodyEl, reg, meta); });
      annot.attach(page.pageEl, page.overlay, p.page);
    });

    function relayout() {
      pager.syncOverlays();
      reg.invalidate();
    }
    relayout();

    if (typeof ResizeObserver !== 'undefined') {
      var ro = new ResizeObserver(relayout);
      ro.observe(container);
    }
    window.addEventListener('resize', relayout);

    /* ── gestures ─────────────────────────────────────────────────────── */

    function strokeToGesture(s) {
      var bbox = NS.polyBBox(s.points);
      /* a marker swipe is a band, not a line — thicken it to what the eye saw */
      if (s.tool === 'marker') {
        bbox = { x: bbox.x, y: bbox.y - 8, w: Math.max(bbox.w, 6), h: Math.max(bbox.h, 0) + 16 };
      }
      return { type: s.tool, page: s.page, points: s.points, bbox: bbox, strokeId: s.id };
    }

    function onGesture(gesture, pageEl) {
      var packet = NS.resolveGesture(gesture, reg, {
        pageEl: pageEl,
        imageOf: function (blockId) { return images[blockId]; },
        blockAt: function (g) {
          var b = pageEl.querySelector('[data-block]');
          var found = null;
          pageEl.querySelectorAll('[data-block]').forEach(function (n) {
            var r = n.getBoundingClientRect(), pb = pageEl.getBoundingClientRect();
            var top = r.top - pb.top, bot = top + r.height;
            var cy = g.bbox.y + g.bbox.h / 2;
            if (cy >= top && cy <= bot) found = n.dataset.block;
          });
          return found;
        }
      });
      emit(packet);
    }

    function emit(packet) {
      lastPacket = packet;
      if (opts.onGesture) opts.onGesture(packet);
      console.log('[nityam:canvas]', packet.gesture, packet);
      persist();
    }

    /* text selection is tier 1 — exact, and worth catching separately */
    function onSelection() {
      if (annot.getTool() !== 'select') return;
      var sel = window.getSelection();
      var page = pager.page(pager.current());
      if (!page) return;
      var hit = annot.anchorsInSelection(sel, page.pageEl);
      if (!hit || !hit.text) return;
      emit(NS.resolveGesture({
        type: 'selection', page: page.no,
        selectedText: hit.text, selectedAnchors: hit.anchors
      }, reg, {}));
    }
    document.addEventListener('mouseup', function () { setTimeout(onSelection, 0); });

    /* ── persistence: a notebook should survive a reload ──────────────── */
    function persist() {
      try {
        localStorage.setItem(STORAGE_KEY + doc.notebook_id,
          JSON.stringify({ strokes: annot.serialise() }));
      } catch (e) { /* private window, blocked storage — not worth failing over */ }
    }
    function restore() {
      try {
        var raw = localStorage.getItem(STORAGE_KEY + doc.notebook_id);
        if (!raw) return 0;
        var saved = JSON.parse(raw);
        annot.restore(saved.strokes);
        pager.pages.forEach(function (p) { annot.redrawPage(p.no, p.overlay); });
        return (saved.strokes || []).length;
      } catch (e) { return 0; }
    }
    var restored = restore();

    /* ── the agent-facing surface ─────────────────────────────────────── */
    var pointTimer = null;
    function pointAt(anchorId, style) {
      var rec = reg.get(anchorId);
      if (!rec || !rec.el) return false;
      pager.goTo(rec.page);
      document.querySelectorAll('.tutor-point').forEach(function (n) { n.classList.remove('tutor-point'); });
      rec.el.classList.add('tutor-point');
      rec.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      clearTimeout(pointTimer);
      if (style !== 'sticky') {
        pointTimer = setTimeout(function () { rec.el.classList.remove('tutor-point'); }, 4200);
      }
      return true;
    }

    return {
      pointAt: pointAt,
      goToPage: function (n) { return pager.goTo(n); },
      nextPage: pager.next,
      prevPage: pager.prev,
      currentPage: pager.current,

      setTool: function (t) { annot.setTool(t); },
      getTool: annot.getTool,
      undo: function () { annot.undo(); persist(); },
      redo: function () { annot.redo(function (n) { return pager.overlayFor(n); }); persist(); },
      clearPage: function () {
        var p = pager.page(pager.current());
        if (p) { annot.clearPage(p.no, p.overlay); persist(); }
      },

      anchors: function () { return reg.all().map(function (r) {
        return { id: r.id, kind: r.kind, page: r.page, block: r.blockId, text: r.text, concept: r.concept };
      }); },
      getAnnotations: annot.serialise,
      lastPacket: function () { return lastPacket; },
      restoredCount: restored,

      /* Insert a block into a page after mount — how the agent will grow the
         notebook turn by turn. */
      addBlock: function (pageNo, block) {
        var page = pager.page(pageNo);
        if (!page) return false;
        NS.renderBlock(block, page.bodyEl, reg, {
          page: pageNo, pageEl: page.pageEl, images: images,
          artifacts: opts.artifacts || {}, themes: opts.themes || {},
          artifactCSS: opts.artifactCSS || '',
          artifactHandles: artifactHandles, onRelayout: relayout
        });
        relayout();
        return true;
      },

      destroy: function () {
        window.removeEventListener('resize', relayout);
        artifactHandles.forEach(function (h) { try { h.destroy(); } catch (e) {} });
        pager.destroy();
        container.innerHTML = '';
      }
    };
  };

})(window.Nityam = window.Nityam || {});
