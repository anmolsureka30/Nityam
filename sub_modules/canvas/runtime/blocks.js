/* Block renderers: CanvasDoc block -> DOM, registering anchors as they go.
 *
 * Every renderer has the same job twice over: draw the thing, and tell the
 * registry which parts of it mean something. A block that renders but registers
 * nothing is invisible to the tutor. */
(function (NS) {

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  /* Wrap each declared `span` of a text block in an anchorable element.
     Sequential scan: earlier anchors win an overlap, and a span that isn't
     found is reported rather than silently dropped. */
  function anchorText(text, anchors, host, reg, meta) {
    var marks = [];
    (anchors || []).forEach(function (a) {
      if (!a.span) return;
      var at = text.indexOf(a.span);
      if (at < 0) {
        console.warn('[nityam:canvas] anchor "' + a.id + '" span not found in ' + meta.blockId);
        return;
      }
      marks.push({ start: at, end: at + a.span.length, a: a });
    });
    marks.sort(function (x, y) { return x.start - y.start; });

    var cursor = 0;
    marks.forEach(function (m) {
      if (m.start < cursor) return;                       // overlap: skip the later one
      if (m.start > cursor) host.appendChild(document.createTextNode(text.slice(cursor, m.start)));
      var span = el('span', 'anc', text.slice(m.start, m.end));
      span.dataset.anchor = m.a.id;
      host.appendChild(span);
      reg.register({
        id: m.a.id, kind: 'text_span', el: span, pageEl: meta.pageEl, page: meta.page,
        blockId: meta.blockId, text: m.a.span,
        concept: m.a.concept, note: m.a.note, misconception: m.a.misconception
      });
      cursor = m.end;
    });
    if (cursor < text.length) host.appendChild(document.createTextNode(text.slice(cursor)));
  }

  /* Equation terms are spans, not a maths library. No external dependency, the
     page runs offline, and every term is independently anchorable — which is
     the entire reason for the choice. */
  function renderTerm(t) {
    var span = el('span', 'term' + (t.plain ? ' plain' : ''));
    if (t.over != null) {
      span.classList.add('frac');
      var num = el('span', 'num', t.over);
      var den = el('span', 'den', t.tex);
      span.appendChild(num); span.appendChild(den);
    } else {
      span.appendChild(document.createTextNode(t.tex));
      if (t.sub) span.appendChild(el('sub', null, t.sub));
      if (t.sup) span.appendChild(el('sup', null, t.sup));
    }
    return span;
  }

  function termText(t) {
    if (t.over != null) return t.over + ' / ' + t.tex;
    return t.tex + (t.sub ? '_' + t.sub : '') + (t.sup ? '^' + t.sup : '');
  }

  var R = {};

  R.heading = function (b, host) { host.appendChild(el('h2', 'blk-h', b.text)); };

  R.tutor_text = function (b, host, reg, meta) {
    var p = el('p', 'blk-p');
    anchorText(b.text, b.anchors, p, reg, meta);
    host.appendChild(p);
  };

  R.callout = function (b, host, reg, meta) {
    var d = el('div', 'blk-callout tone-' + (b.tone || 'neutral'));
    var body = el('div', 'callout-body');
    anchorText(b.text, b.anchors, body, reg, meta);
    d.appendChild(body);
    host.appendChild(d);
  };

  R.equation = function (b, host, reg, meta) {
    var wrap = el('div', 'blk-eq');
    var row = el('div', 'eq-row');
    (b.terms || []).forEach(function (t) {
      var span = renderTerm(t);
      row.appendChild(span);
      if (t.plain) return;
      span.dataset.anchor = t.id;
      span.classList.add('anc');
      reg.register({
        id: t.id, kind: 'equation_term', el: span, pageEl: meta.pageEl, page: meta.page,
        blockId: meta.blockId, text: termText(t),
        concept: t.concept, note: t.note, misconception: t.misconception
      });
    });
    wrap.appendChild(row);
    host.appendChild(wrap);
  };

  R.diagram = function (b, host, reg, meta) {
    var wrap = el('figure', 'blk-fig');
    var box = el('div', 'fig-box');
    box.innerHTML = b.svg;
    wrap.appendChild(box);
    if (b.caption) wrap.appendChild(el('figcaption', null, b.caption));
    host.appendChild(wrap);

    (b.anchors || []).forEach(function (a) {
      if (!a.element) return;
      var target = box.querySelector(a.element);
      if (!target) {
        console.warn('[nityam:canvas] anchor "' + a.id + '" selector ' + a.element + ' not found');
        return;
      }
      target.classList.add('anc-svg');
      target.dataset.anchor = a.id;
      reg.register({
        id: a.id, kind: 'diagram_element', el: target, pageEl: meta.pageEl, page: meta.page,
        blockId: meta.blockId, text: a.element,
        concept: a.concept, note: a.note, misconception: a.misconception
      });
    });
  };

  R.image = function (b, host, reg, meta) {
    var wrap = el('figure', 'blk-fig');
    var box = el('div', 'fig-box img-box');
    var img = el('img', 'blk-img');
    img.src = b.src;
    img.alt = b.alt || '';
    img.draggable = false;
    box.appendChild(img);
    wrap.appendChild(box);

    var cap = el('figcaption');
    if (b.kind) {
      var chip = el('span', 'prov', b.kind === 'generated' ? 'AI-generated'
                                : b.kind === 'web' ? 'from the web' : 'photo');
      cap.appendChild(chip);
    }
    if (b.caption) cap.appendChild(document.createTextNode(b.caption));
    wrap.appendChild(cap);
    host.appendChild(wrap);

    meta.images[b.id] = img;

    (b.regions || []).forEach(function (rg) {
      reg.register({
        id: rg.id, kind: 'image_region', el: img, pageEl: meta.pageEl, page: meta.page,
        blockId: meta.blockId, text: rg.label || rg.id, frac: rg.rect,
        concept: rg.concept, note: rg.note
      });
    });
    /* re-measure once the bitmap has actually laid out */
    img.addEventListener('load', function () { reg.invalidate(); if (meta.onRelayout) meta.onRelayout(); });
  };

  /* The notebook can hold a LIVE artifact, not a picture of one. Same runtime,
     same namespace — this is the whole integration with artifact_generator. */
  /* The notebook can hold a LIVE artifact, not a picture of one. Same runtime,
     same namespace — this is the whole integration with artifact_generator.
     `host` here is already the .blk.blk-artifact wrapper renderBlock made. */
  R.artifact = function (b, host, reg, meta) {
    var ir = (meta.artifacts || {})[b.artifact_ir];
    if (!ir) {
      host.appendChild(el('div', 'blk-missing', 'Artifact not bundled: ' + b.artifact_ir));
      return;
    }
    if (!NS.mountArtifact) {
      host.appendChild(el('div', 'blk-missing', 'Artifact runtime not loaded.'));
      return;
    }

    /* Shadow root, deliberately. The artifact ships its own stylesheet whose
       class names (.card, .btn, .top) are generic enough to collide with the
       notebook's in both directions. Encapsulation is one line and settles it;
       CSS custom properties still inherit through, so the two surfaces keep
       sharing one design system. */
    var mountTarget = host;
    if (host.attachShadow && meta.artifactCSS) {
      var shadow = host.attachShadow({ mode: 'open' });
      var st = document.createElement('style');
      st.textContent = meta.artifactCSS;
      shadow.appendChild(st);
      mountTarget = document.createElement('div');
      mountTarget.className = 'nty-artifact-host';
      shadow.appendChild(mountTarget);
    }

    var handle = NS.mountArtifact(ir, mountTarget, {
      themes: meta.themes || {},
      theme: b.theme,
      onEvidence: function (e) { if (meta.onArtifactEvidence) meta.onArtifactEvidence(e, b.id); }
    });
    meta.artifactHandles.push(handle);

    reg.register({
      id: b.id + '__artifact', kind: 'artifact', el: host, pageEl: meta.pageEl, page: meta.page,
      blockId: b.id,
      text: 'the ' + (ir.intent && ir.intent.concept_ids ? ir.intent.concept_ids[0] : '') + ' simulator',
      note: 'A live interactive artifact; it reports its own evidence separately.'
    });
  };

  R.student_work = function (b, host, reg, meta) {
    var wrap = el('div', 'blk-work');
    wrap.appendChild(el('div', 'work-label', b.prompt || 'Your working'));
    var area = el('div', 'work-area');
    area.style.minHeight = (b.height || 140) + 'px';
    var ta = el('textarea', 'work-input');
    ta.placeholder = 'Type here, or use the marker to write on the page.';
    ta.rows = 3;
    area.appendChild(ta);
    wrap.appendChild(area);
    host.appendChild(wrap);

    reg.register({
      id: b.id + '__work', kind: 'student_work', el: area, pageEl: meta.pageEl, page: meta.page,
      blockId: b.id, text: b.prompt || 'the student working area',
      note: "The student's own working space."
    });
  };

  NS.BLOCKS = R;

  NS.renderBlock = function (b, host, reg, meta) {
    var fn = R[b.type];
    if (!fn) {
      console.warn('[nityam:canvas] unknown block type: ' + b.type);
      return;
    }
    var wrap = el('div', 'blk blk-' + b.type);
    wrap.dataset.block = b.id;
    host.appendChild(wrap);
    try {
      fn(b, wrap, reg, Object.assign({}, meta, { blockId: b.id }));
    } catch (e) {
      /* one bad block must not take the rest of the notebook down with it */
      console.error('[nityam:canvas] block "' + b.id + '" (' + b.type + ') failed:', e);
      wrap.appendChild(el('div', 'blk-missing', 'This block could not be rendered.'));
    }
  };

})(window.Nityam = window.Nityam || {});
