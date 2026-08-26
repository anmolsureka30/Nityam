/* The notebook surface: discrete pages in one scroller, read like a PDF.
 *
 * Not an infinite canvas. Pages have edges, they come in order, and a scroll
 * position means something — which is what makes a notebook feel like a
 * notebook, and what makes annotations easy to anchor. */
(function (NS) {

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  NS.createPager = function (doc, host, opts) {
    var pages = [];             // { no, label, pageEl, bodyEl, overlay }
    var current = 1;

    var scroller = el('div', 'nb-scroll');
    host.appendChild(scroller);

    doc.pages.forEach(function (p) {
      var pageEl = el('section', 'nb-page');
      pageEl.dataset.page = p.page;
      pageEl.setAttribute('aria-label', 'Page ' + p.page + (p.label ? ': ' + p.label : ''));

      var body = el('div', 'nb-body');
      pageEl.appendChild(body);

      /* one transparent SVG per page, on top of the content, in page coords */
      var overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      overlay.setAttribute('class', 'nb-overlay');
      overlay.dataset.page = p.page;
      pageEl.appendChild(overlay);

      var foot = el('div', 'nb-foot');
      foot.appendChild(el('span', 'nb-lab', p.label || ''));
      foot.appendChild(el('span', 'nb-num', String(p.page)));
      pageEl.appendChild(foot);

      scroller.appendChild(pageEl);
      pages.push({ no: p.page, label: p.label || '', pageEl: pageEl, bodyEl: body, overlay: overlay });
    });

    /* Which page is the reader actually looking at? The one covering the most
       of the viewport, not merely the first one intersecting it. */
    var io = null;
    if (typeof IntersectionObserver !== 'undefined') {
      var ratios = {};
      io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { ratios[e.target.dataset.page] = e.intersectionRatio; });
        var best = current, bestR = -1;
        Object.keys(ratios).forEach(function (k) {
          if (ratios[k] > bestR) { bestR = ratios[k]; best = parseInt(k, 10); }
        });
        if (best !== current) {
          current = best;
          if (opts.onPageChange) opts.onPageChange(current);
        }
      }, { root: scroller, threshold: [0, 0.25, 0.5, 0.75, 1] });
      pages.forEach(function (p) { io.observe(p.pageEl); });
    }

    function goTo(n, behavior) {
      var p = pages.filter(function (x) { return x.no === n; })[0];
      if (!p) return false;
      p.pageEl.scrollIntoView({ behavior: behavior || 'smooth', block: 'start' });
      current = n;
      if (opts.onPageChange) opts.onPageChange(n);
      return true;
    }

    return {
      scroller: scroller,
      pages: pages,
      page: function (n) { return pages.filter(function (p) { return p.no === n; })[0]; },
      overlayFor: function (n) { var p = this.page(n); return p && p.overlay; },
      current: function () { return current; },
      goTo: goTo,
      next: function () { return goTo(Math.min(current + 1, pages.length)); },
      prev: function () { return goTo(Math.max(current - 1, 1)); },

      /* the overlay's coordinate system must track the page box exactly */
      syncOverlays: function () {
        pages.forEach(function (p) {
          var r = p.pageEl.getBoundingClientRect();
          p.overlay.setAttribute('viewBox', '0 0 ' + Math.round(r.width) + ' ' + Math.round(r.height));
          p.overlay.setAttribute('width', Math.round(r.width));
          p.overlay.setAttribute('height', Math.round(r.height));
        });
      },

      destroy: function () { if (io) io.disconnect(); }
    };
  };

})(window.Nityam = window.Nityam || {});
