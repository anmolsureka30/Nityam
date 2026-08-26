/* Pure geometry + scoring tests for the resolver. No browser, no DOM.
 *
 *   node tests/resolve.js
 *
 * These are the tests worth having: coverage scoring is what decides whether a
 * sloppy circle produces one confident wrong answer or an honest "probably this,
 * possibly that", and it is pure arithmetic that can be pinned down exactly. */
const path = require('path');
const B = process.argv[2] || path.join(__dirname, '..');
const NS = require(path.join(B, 'runtime', 'resolve.js'));

let pass = 0, fail = 0;
function eq(name, got, want, tol) {
  const ok = tol == null ? got === want : Math.abs(got - want) <= tol;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}` + (ok ? '' : `   got ${got}, want ${want}`));
  ok ? pass++ : fail++;
}
function ok_(name, cond, note) {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${note ? '   ' + note : ''}`);
  cond ? pass++ : fail++;
}

/* a fake registry over synthetic rects — exactly the shape anchors.js produces */
function reg(anchors) {
  const byId = {};
  anchors.forEach(a => { byId[a.id] = a; });
  return {
    get: id => byId[id],
    all: () => anchors,
    onPage: p => anchors.filter(a => a.page === p),
    describe: (rec, c) => ({
      anchor: rec.id, kind: rec.kind, text: rec.text, block: rec.blockId,
      coverage: Math.round(c * 100) / 100, concept: rec.concept
    })
  };
}
const box = (id, x, y, w, h, extra) => Object.assign(
  { id, kind: 'equation_term', page: 1, blockId: 'b1', text: id,
    boxes: [{ x, y, w, h }], rect: { x, y, w, h } }, extra || {});

const rectPoly = (x, y, w, h) => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

console.log('\n─ coverage geometry ─');
eq('polygon fully containing a box', NS.polygonCoverage({ x: 20, y: 20, w: 10, h: 10 }, rectPoly(0, 0, 100, 100)), 1);
eq('polygon missing a box entirely', NS.polygonCoverage({ x: 200, y: 0, w: 10, h: 10 }, rectPoly(0, 0, 100, 100)), 0);
eq('polygon covering the left half', NS.polygonCoverage({ x: 90, y: 40, w: 20, h: 10 }, rectPoly(0, 0, 100, 100)), 0.5, 0.01);
eq('bbox of a polygon', JSON.stringify(NS.polyBBox(rectPoly(5, 7, 20, 30))), JSON.stringify({ x: 5, y: 7, w: 20, h: 30 }));

console.log('\n─ marker: a swipe is a band, not an enclosure ─');
{
  const a = box('t_usin', 100, 100, 80, 30);
  const g = { type: 'marker', page: 1, bbox: { x: 95, y: 98, w: 90, h: 34 } };
  eq('marker across a term scores high', NS.scoreAnchor(a, g), 1, 0.01);

  const b = box('t_2g', 300, 100, 40, 30);
  ok_('marker nowhere near another term scores 0', NS.scoreAnchor(b, g) === 0);

  // a stacked fraction is much taller than the swipe band - area-intersection
  // would score this ~0.27 and drop it below the floor, which is wrong
  const frac = box('t_frac', 100, 80, 80, 66);
  const swipe = { type: 'marker', page: 1, bbox: { x: 96, y: 105, w: 88, h: 16 } };
  const fs = NS.scoreAnchor(frac, swipe);
  ok_('marker across a TALL fraction still resolves it', fs >= NS.RESOLVE_FLOOR,
      `score=${fs.toFixed(2)} (area-intersection would give ~0.27)`);

  const half = { type: 'marker', page: 1, bbox: { x: 96, y: 105, w: 44, h: 16 } };
  eq('  half a swipe scores about half', NS.scoreAnchor(frac, half), 0.5, 0.08);

  const above = { type: 'marker', page: 1, bbox: { x: 96, y: 20, w: 88, h: 16 } };
  eq('  a swipe above the term scores 0', NS.scoreAnchor(frac, above), 0);
}

console.log('\n─ circle: clean vs sloppy ─');
{
  const usin = box('t_usin', 100, 100, 80, 30, { concept: 'projectile.max_height' });
  const twog = box('t_2g', 200, 100, 40, 30);
  const R = reg([usin, twog]);

  // tight circle around one term only
  const tight = { type: 'circle', page: 1, points: rectPoly(92, 92, 96, 46) };
  tight.bbox = NS.polyBBox(tight.points);
  const p1 = NS.resolveGesture(tight, R, {});
  ok_('tight circle resolves exactly one anchor', p1.resolved.length === 1 && p1.nearby.length === 0,
      `resolved=[${p1.resolved.map(r => r.anchor)}]`);
  eq('  and its confidence is high', p1.confidence, 1, 0.01);
  ok_('  concept comes through', p1.resolved[0].concept === 'projectile.max_height');
  ok_('  tier is geometry', p1.tier === 'geometry');

  // sloppy circle spanning both, clipping each
  const sloppy = { type: 'circle', page: 1, points: rectPoly(150, 105, 90, 20) };
  sloppy.bbox = NS.polyBBox(sloppy.points);
  const p2 = NS.resolveGesture(sloppy, R, {});
  ok_('sloppy circle touches both terms', p2.resolved.length + p2.nearby.length === 2,
      `resolved=${p2.resolved.length} nearby=${p2.nearby.length}`);
  ok_('  neither reaches full confidence', p2.confidence < 0.95, `confidence=${p2.confidence}`);
  ok_('  results are ranked by coverage',
      (p2.resolved.concat(p2.nearby)).every((r, i, arr) => i === 0 || arr[i - 1].coverage >= r.coverage));

  // a circle in the empty margin
  const empty = { type: 'circle', page: 1, points: rectPoly(600, 600, 60, 40) };
  empty.bbox = NS.polyBBox(empty.points);
  const p3 = NS.resolveGesture(empty, R, {});
  ok_('empty margin resolves nothing', p3.resolved.length === 0 && p3.nearby.length === 0);
  ok_('  but the packet is still well-formed',
      p3.gesture === 'circle' && p3.confidence === 0 && p3.block === null && Array.isArray(p3.bbox));
}

console.log('\n─ the resolve floor ─');
{
  const a = box('a', 100, 100, 100, 100);
  const R = reg([a]);
  // cover ~25% of the anchor: below RESOLVE_FLOOR, so it is context not referent
  const g = { type: 'circle', page: 1, points: rectPoly(100, 100, 50, 50) };
  g.bbox = NS.polyBBox(g.points);
  const p = NS.resolveGesture(g, R, {});
  ok_(`a quarter-covered anchor lands in nearby, not resolved (floor ${NS.RESOLVE_FLOOR})`,
      p.nearby.length === 1 && p.resolved.length === 0, `coverage=${(p.nearby[0]||{}).coverage}`);
}

console.log('\n─ selection is tier 1: exact, no geometry ─');
{
  const a = Object.assign(box('a_vert', 0, 0, 1, 1), { kind: 'text_span', text: 'vertical component' });
  const R = reg([a]);
  const p = NS.resolveGesture({
    type: 'selection', page: 1, selectedText: 'vertical component', selectedAnchors: ['a_vert']
  }, R, {});
  ok_('selection resolves the anchor', p.resolved.length === 1 && p.resolved[0].anchor === 'a_vert');
  eq('  with confidence 1', p.confidence, 1);
  ok_('  and reports tier=selection', p.tier === 'selection');
  ok_('  carrying the selected text', p.selected_text === 'vertical component');
}

console.log('\n─ wrapped phrases (a span across two lines) ─');
{
  const wrapped = { id: 'a_wrap', kind: 'text_span', page: 1, blockId: 'b1', text: 'horizontal component',
                    boxes: [{ x: 400, y: 100, w: 120, h: 22 }, { x: 60, y: 126, w: 90, h: 22 }] };
  const g = { type: 'marker', page: 1, bbox: { x: 395, y: 96, w: 130, h: 30 } };
  const s = NS.scoreAnchor(wrapped, g);
  ok_('a marker over one line of a wrapped phrase still resolves it', s >= NS.RESOLVE_FLOOR,
      `score=${s.toFixed(2)} (area-weighted would be ~0.5)`);
}

console.log(`\n  ${fail === 0 ? 'RESOLVE TESTS: PASS' : 'RESOLVE TESTS: FAIL'}  (${pass} passed, ${fail} failed)\n`);
process.exit(fail === 0 ? 0 : 1);
