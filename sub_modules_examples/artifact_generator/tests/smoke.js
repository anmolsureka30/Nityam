/* Headless smoke test for the runtime. Requires node, no browser.
 *
 *   node tests/smoke.js
 *   IR=examples/lesson2_gravity.json node tests/smoke.js
 *
 * Checks the JS kernel still matches the Python twin, then replays a student
 * session against the IR and asserts the right evidence events fire. */
const fs = require('fs'), vm = require('vm'), path = require('path');
const B = process.argv[2] || path.join(__dirname, '..');
const { loadIR, drivePlan, expectedOnceEvents } = require('./lib.js');

const sandbox = { window: {}, console, Date, Math, JSON, setTimeout, clearTimeout, document: null };
vm.createContext(sandbox);
for (const f of ['kernel.js', 'evaluate.js', 'probes.js', 'render.js', 'mount.js']) {
  const src = fs.readFileSync(path.join(B, 'runtime', f), 'utf8');
  try { vm.runInContext(src, sandbox, { filename: f }); console.log('  load  OK   ' + f); }
  catch (e) { console.log('  load  FAIL ' + f + ' :: ' + e.message); process.exit(1); }
}
const NS = sandbox.window.Nityam;
const ir = loadIR(B);
const themes = JSON.parse(fs.readFileSync(path.join(B, 'examples', 'themes.json'), 'utf8'));
const theme = themes.cricket;

console.log('\n  lesson: ' + ir.artifact_id);

/* kernel parity against the Python twin */
const parity = JSON.parse(fs.readFileSync(path.join(B, 'out', 'parity.json'), 'utf8'));
let worst = 0;
for (const v of parity) {
  const got = NS.KERNELS[ir.kernel](v.in);
  for (const k in v.out) worst = Math.max(worst, Math.abs(got[k] - v.out[k]));
}
console.log('  parity  max |python - js| = ' + worst.toExponential(2) + (worst < 1e-9 ? '  OK' : '  DRIFT'));

/* ---- replay an exploring student ------------------------------------- */
const plan = drivePlan(ir);
console.log('\n  --- replay: ' + plan.name + ' -> ' + plan.values.join(', ') + ' ---');
let state = NS.defaultState(ir);
const events = [];
const probes = NS.createProbeEngine(ir, e => {
  events.push(e);
  console.log('  EVIDENCE  ' + e.event + '  ' + JSON.stringify(e.payload) +
    (e.concept ? '  [' + e.concept + ']' : '') + (e.misconception ? '  [!' + e.misconception + ']' : ''));
});
for (const v of plan.values) {
  state[plan.name] = v;
  const f = NS.evaluate(ir, state, theme);
  probes.onSettle(plan.controlId, f);
}
const wantOnce = expectedOnceEvents(ir);
const gotOnce = wantOnce.filter(w => events.some(e => e.event === w));
console.log('  ' + plan.probeId + ' count = ' + probes.count(plan.probeId));
console.log('  discovery events: ' + (gotOnce.join(', ') || '(none)') + '   expected: ' + wantOnce.join(', '));

/* ---- replay the misconception path ----------------------------------- */
const miscProbe = ir.probes.find(p => p.misconception && p.on === 'predicate');
let gotMisc = true;
if (miscProbe) {
  const need = (miscProbe.when.all || []).find(c => c.distinct_settled && c.distinct_settled.gte);
  const cid = need.distinct_settled.control;
  const ctrl = ir.controls.find(c => c.id === cid), nm = ctrl.bind.split('.')[1], sv = ir.state[nm];
  console.log('\n  --- replay: ' + nm + ' only, everything else untouched ---');
  let s2 = NS.defaultState(ir);
  const ev2 = [];
  const p2 = NS.createProbeEngine(ir, e => { ev2.push(e); console.log('  EVIDENCE  ' + e.event + (e.misconception ? '  [!' + e.misconception + ']' : '')); });
  [0.3, 0.5, 0.7].forEach(f => { s2[nm] = Math.round(sv.min + (sv.max - sv.min) * f); p2.onSettle(cid, NS.evaluate(ir, s2, theme)); });
  gotMisc = ev2.some(e => e.event === 'artifact.misconception_behavior');
  console.log('  misconception_behavior fired: ' + gotMisc);
}

const ok = worst < 1e-9 && gotOnce.length === wantOnce.length && gotMisc && probes.count(plan.probeId) >= 3;
console.log('\n  SMOKE: ' + (ok ? 'PASS' : 'FAIL'));
process.exit(ok ? 0 : 1);
