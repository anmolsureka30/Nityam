/* Copied from sub_modules_examples/artifact_generator/runtime/ with one edit:
 * the IIFE receives the local NS below instead of window.Nityam. */
import { NS } from "./ns.js";

/* The probe engine: turns interaction into concept-tagged evidence.
 *
 * This is the part that makes an artifact a diagnostic instrument rather than a
 * visualisation. In the real product `emit` posts to the Learning Agent, which
 * calls update_student_memory(). Here it renders into the evidence stream so
 * you can watch it happen. */
(function (NS) {

  NS.createProbeEngine = function (ir, emit) {
    var settled = {};    // controlId -> { value: true }  (distinct parked values)
    var maxSeen = {};    // "derived.range" -> number
    var fired = {};      // probeId -> true
    var counts = {};     // probeId -> how many times it emitted

    function distinctSettled(cid) { return Object.keys(settled[cid] || {}).length; }

    function refValue(ref, frame) {
      var i = ref.indexOf('.');
      return NS.resolveRef(ref, frame);
    }

    function noteMax(ref, frame) {
      var v = refValue(ref, frame);
      if (typeof v !== 'number') return;
      if (maxSeen[ref] === undefined || v > maxSeen[ref]) maxSeen[ref] = v;
    }

    /* Structured conditions - data, not code, so they were validated at build time. */
    function evalCondition(cond, frame) {
      if (!cond) return false;
      if (cond.all) return cond.all.every(function (c) { return evalCondition(c, frame); });
      if (cond.any) return cond.any.some(function (c) { return evalCondition(c, frame); });

      if (cond.near) {
        var v = refValue(cond.near.ref, frame);
        return typeof v === 'number' && Math.abs(v - cond.near.value) <= (cond.near.tol == null ? 1e-9 : cond.near.tol);
      }
      if (cond.distinct_settled) {
        var d = cond.distinct_settled, n = distinctSettled(d.control);
        if (d.gte != null) return n >= d.gte;
        if (d.eq != null) return n === d.eq;
        return false;
      }
      if (cond.is_max_seen) {
        var r = cond.is_max_seen.ref, cur = refValue(r, frame);
        return typeof cur === 'number' && maxSeen[r] !== undefined && cur >= maxSeen[r] - 1e-9;
      }
      return false;
    }
    NS.evalCondition = evalCondition;   // reused by annotation layers

    function fire(probe, frame) {
      var payload = {};
      (probe.payload || []).forEach(function (ref) {
        var v = refValue(ref, frame);
        payload[ref] = typeof v === 'number' ? Math.round(v * 100) / 100 : v;
      });
      counts[probe.id] = (counts[probe.id] || 0) + 1;
      if (probe.once) fired[probe.id] = true;

      emit({
        t: Date.now(),
        probe: probe.id,
        event: probe.emit,
        concept: probe.concept || null,
        misconception: probe.misconception || null,
        note: probe.note || null,
        student_text: probe.student_text || null,
        payload: payload
      });
    }

    function evaluatePredicates(frame) {
      ir.probes.forEach(function (p) {
        if (p.on !== 'predicate' || fired[p.id]) return;
        if (evalCondition(p.when, frame)) fire(p, frame);
      });
    }

    return {
      /* Called ~400ms after the student stops dragging a control. */
      onSettle: function (controlId, frame) {
        settled[controlId] = settled[controlId] || {};
        var ctrl = ir.controls.filter(function (c) { return c.id === controlId; })[0];
        if (ctrl && ctrl.bind) settled[controlId][NS.resolveRef(ctrl.bind, frame)] = true;

        ir.probes.forEach(function (p) { if (p.payload) p.payload.forEach(function (r) { noteMax(r, frame); }); });

        ir.probes.forEach(function (p) {
          if (p.on === 'control_settle' && p.control === controlId && !fired[p.id]) fire(p, frame);
        });
        evaluatePredicates(frame);
      },
      count: function (probeId) { return counts[probeId] || 0; },
      state: function () { return { settled: settled, maxSeen: maxSeen, counts: counts }; }
    };
  };

})(NS);
