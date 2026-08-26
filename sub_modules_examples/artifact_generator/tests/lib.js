/* Shared test helpers: work out how to drive ANY lesson IR, rather than
 * hard-coding lesson 1's sliders. */
const fs = require('fs'), path = require('path');

function loadIR(B) {
  return JSON.parse(fs.readFileSync(process.env.IR || path.join(B, 'examples', 'lesson1_max_range.json'), 'utf8'));
}

/* The control the first exploration probe watches, and a sequence of values
 * that should satisfy every `once` predicate probe hanging off it. */
function drivePlan(ir) {
  const explore = ir.probes.find(p => p.on === 'control_settle');
  if (!explore) return null;
  const ctrl = ir.controls.find(c => c.id === explore.control);
  const name = ctrl.bind.split('.')[1];
  const sv = ir.state[name];

  // any `near` target the predicate probes want us to land on
  const targets = [];
  function scan(c) {
    if (!c) return;
    (c.all || []).concat(c.any || []).forEach(scan);
    if (c.near && c.near.ref === 'state.' + name) targets.push(c.near.value);
  }
  ir.probes.filter(p => p.on === 'predicate').forEach(p => scan(p.when));

  const goal = targets.length ? targets[0] : (sv.min + sv.max) / 2;
  // three distinct warm-up values that are NOT the goal, then the goal last
  const warm = [0.25, 0.55, 0.8]
    .map(f => Math.round(sv.min + (sv.max - sv.min) * f))
    .filter(v => Math.abs(v - goal) > (sv.step || 1) * 2);
  return { probeId: explore.id, controlId: ctrl.id, name, values: warm.slice(0, 3).concat([goal]) };
}

function expectedOnceEvents(ir) {
  return ir.probes.filter(p => p.on === 'predicate' && p.once && !p.misconception).map(p => p.emit);
}

module.exports = { loadIR, drivePlan, expectedOnceEvents };
