"""
The validation gate.

Four passes, all mechanical, all run BEFORE the artifact reaches a student:

  1. structural   - required keys, types, enums          (shape)
  2. referential  - every ref/binding actually resolves  (wiring)
  3. invariants   - sweep the kernel, assert properties  (physics)
  4. pedagogical  - does a control actually move the
                    quantity the learning outcome is
                    about?                               (teaching value)

Pass 4 is the one nobody builds, and it is the one that catches a beautiful
artifact whose slider does nothing relevant.

Zero third-party dependencies. If `jsonschema` happens to be installed we run
it too, as a bonus pass.
"""

import math
import re

from kernel_py import KERNELS, KERNEL_PORTS, KERNEL_OUTPUTS

REF_RE = re.compile(r"^(state|kernel|derived|point)\.([a-zA-Z_][a-zA-Z0-9_]*)$")

LAYER_TYPES = {"scene2d", "trace", "trace_set", "vector", "vector_set", "readout_group", "annotation"}

# `point.*` is only meaningful inside a vector_set, which is evaluated once per
# sampled point along the trajectory rather than once per frame.
POINT_FIELDS = {"x", "y", "t", "vx", "vy"}
WIDGETS = {"slider", "button"}
ACTIONS = {"snapshot", "clear_snapshots"}


class Report:
    def __init__(self):
        self.errors = []
        self.checks = []      # (name, ok, detail)

    def err(self, msg):
        self.errors.append(msg)

    def check(self, name, ok, detail="", info=""):
        """detail = why it failed; info = something worth showing even on success."""
        self.checks.append((name, bool(ok), info if ok else detail))
        if not ok:
            self.errors.append(f"{name}: {detail}")

    @property
    def ok(self):
        return not self.errors


# ---------------------------------------------------------------- helpers

def resolve(ref, ctx):
    """Resolve 'state.theta' / 'kernel.range' / 'derived.range' against a frame."""
    if isinstance(ref, (int, float)):
        return ref
    m = REF_RE.match(str(ref))
    if not m:
        return None
    ns, name = m.groups()
    return ctx.get(ns, {}).get(name)


class UnwiredIR(Exception):
    """A ref did not resolve. Raised so the validator can REPORT rather than crash."""


def evaluate(ir, state_values):
    """Run one full evaluation cycle in Python - the mirror of runtime/evaluate.js."""
    kfn = KERNELS.get(ir.get("kernel"))
    if kfn is None:
        raise UnwiredIR(f"unknown kernel {ir.get('kernel')!r}")
    inputs = {}
    for port, ref in ir["kernel_inputs"].items():
        v = ref if isinstance(ref, (int, float)) else resolve(ref, {"state": state_values})
        if v is None:
            raise UnwiredIR(f"kernel port '{port}' <- {ref!r} did not resolve")
        inputs[port] = v
    try:
        kernel = kfn(**inputs)
    except TypeError as e:
        raise UnwiredIR(f"kernel call failed: {e}")
    derived = {k: resolve(ref, {"state": state_values, "kernel": kernel})
               for k, ref in ir.get("derived", {}).items()}
    return {"state": state_values, "kernel": kernel, "derived": derived}


def defaults(ir):
    return {k: v["value"] for k, v in ir["state"].items()}


# ---------------------------------------------------------------- pass 1

def structural(ir, r):
    required = ["ir_version", "artifact_id", "kernel", "intent", "state",
                "kernel_inputs", "derived", "controls", "layers", "probes"]
    missing = [k for k in required if k not in ir]
    r.check("structure.required_keys", not missing, f"missing {missing}")
    if missing:
        return

    r.check("structure.ir_version", ir["ir_version"] == "0.1", f"got {ir['ir_version']!r}")
    r.check("structure.kernel_known", ir["kernel"] in KERNELS,
            f"{ir['kernel']!r} not in registry {sorted(KERNELS)}")

    intent = ir["intent"]
    r.check("structure.intent", bool(intent.get("concept_ids")) and bool(intent.get("learning_outcome")),
            "intent needs concept_ids and learning_outcome")

    for name, sv in ir["state"].items():
        if "value" not in sv or "unit" not in sv:
            r.err(f"structure.state: '{name}' needs value and unit")
        if not sv.get("locked") and ("min" not in sv or "max" not in sv):
            r.err(f"structure.state: unlocked var '{name}' needs min and max")

    for c in ir["controls"]:
        if c.get("widget") not in WIDGETS:
            r.err(f"structure.controls: '{c.get('id')}' bad widget {c.get('widget')!r}")
        if c.get("widget") == "button" and c.get("action") not in ACTIONS:
            r.err(f"structure.controls: button '{c.get('id')}' bad action {c.get('action')!r}")

    for ly in ir["layers"]:
        if ly.get("type") not in LAYER_TYPES:
            r.err(f"structure.layers: unknown layer type {ly.get('type')!r}")


# ---------------------------------------------------------------- pass 2

def referential(ir, r):
    """Every binding must point at something that exists. This is the pass that
    catches an LLM inventing `state.velocity` when the artifact declared `state.u`."""
    state_names = set(ir["state"])
    kernel_outs = set(KERNEL_OUTPUTS[ir["kernel"]])
    derived_names = set(ir.get("derived", {}))
    control_ids = {c["id"] for c in ir["controls"]}
    probe_ids = {p["id"] for p in ir["probes"]}

    # kernel port mapping
    ports = set(KERNEL_PORTS[ir["kernel"]])
    for port, ref in ir["kernel_inputs"].items():
        if port not in ports:
            r.err(f"ref.kernel_inputs: '{port}' is not a port of {ir['kernel']} {sorted(ports)}")
        if isinstance(ref, str):
            m = REF_RE.match(ref)
            if not m or m.group(1) != "state" or m.group(2) not in state_names:
                r.err(f"ref.kernel_inputs: port '{port}' -> {ref!r} does not resolve")

    def check_ref(ref, where, allow=("state", "kernel", "derived")):
        m = REF_RE.match(str(ref))
        if not m:
            r.err(f"ref.{where}: {ref!r} is not a valid ref")
            return
        ns, name = m.groups()
        if ns not in allow:
            r.err(f"ref.{where}: namespace '{ns}' not allowed here")
        elif ns == "state" and name not in state_names:
            r.err(f"ref.{where}: state.{name} is not declared")
        elif ns == "kernel" and name not in kernel_outs:
            r.err(f"ref.{where}: kernel.{name} is not an output of {ir['kernel']}")
        elif ns == "derived" and name not in derived_names:
            r.err(f"ref.{where}: derived.{name} is not declared")

    for k, ref in ir.get("derived", {}).items():
        check_ref(ref, f"derived.{k}", allow=("state", "kernel"))

    for c in ir["controls"]:
        if c.get("bind"):
            check_ref(c["bind"], f"controls.{c['id']}.bind", allow=("state",))
            nm = c["bind"].split(".")[1]
            if ir["state"].get(nm, {}).get("locked"):
                r.err(f"ref.controls: '{c['id']}' binds locked state var '{nm}'")

    for ly in ir["layers"]:
        t = ly["type"]
        if t == "trace":
            check_ref(ly.get("points"), "layers.trace.points", allow=("kernel",))
        if t == "vector":
            check_ref(ly.get("at"), "layers.vector.at", allow=("kernel", "state"))
            for axis, ref in (ly.get("components") or {}).items():
                check_ref(ref, f"layers.vector.components.{axis}")
        if t == "vector_set":
            for axis, ref in (ly.get("components") or {}).items():
                m = REF_RE.match(str(ref))
                if m and m.group(1) == "point":
                    if m.group(2) not in POINT_FIELDS:
                        r.err(f"ref.layers.vector_set: point.{m.group(2)} is not a path field {sorted(POINT_FIELDS)}")
                else:
                    check_ref(ref, f"layers.vector_set.components.{axis}")
        if t == "readout_group":
            for it in ly.get("items", []):
                check_ref(it.get("value"), "layers.readout_group.items.value")
        if ly.get("when"):
            check_condition(ly["when"], f"layers.{t}.when", control_ids, check_ref, r)

    for p in ir["probes"]:
        if p["on"] == "control_settle" and p.get("control") not in control_ids:
            r.err(f"ref.probes: '{p['id']}' watches unknown control {p.get('control')!r}")
        if p["on"] == "predicate" and not p.get("when"):
            r.err(f"ref.probes: predicate probe '{p['id']}' has no `when`")
        if p.get("when"):
            check_condition(p["when"], f"probes.{p['id']}.when", control_ids, check_ref, r)
        for ref in p.get("payload", []):
            check_ref(ref, f"probes.{p['id']}.payload")

    for q in ir.get("assessment", []):
        g = q.get("gate")
        if g and g.get("probe") not in probe_ids:
            r.err(f"ref.assessment: '{q['id']}' gated on unknown probe {g.get('probe')!r}")
        if q.get("expected") not in q.get("options", []):
            r.err(f"ref.assessment: '{q['id']}' expected {q.get('expected')} is not among options")

    r.check("ref.integrity", not any(e.startswith("ref.") for e in r.errors),
            "some bindings do not resolve")


def check_condition(cond, where, control_ids, check_ref, r):
    if "all" in cond or "any" in cond:
        for sub in cond.get("all", []) + cond.get("any", []):
            check_condition(sub, where, control_ids, check_ref, r)
        return
    if "near" in cond:
        check_ref(cond["near"].get("ref"), where)
    if "is_max_seen" in cond:
        check_ref(cond["is_max_seen"].get("ref"), where)
    if "distinct_settled" in cond:
        cid = cond["distinct_settled"].get("control")
        if cid not in control_ids:
            r.err(f"ref.{where}: distinct_settled on unknown control {cid!r}")


# ---------------------------------------------------------------- pass 3 + 4

def run_invariants(ir, r):
    base = defaults(ir)

    # An unwired IR cannot be swept. Report that plainly instead of crashing -
    # the referential pass has already said exactly which refs are broken.
    try:
        evaluate(ir, base)
    except UnwiredIR as e:
        r.check("invariant.sweep", False, f"skipped - IR is not wired up ({e})")
        return

    for inv in ir.get("invariants", []):
        chk = inv["check"]

        if chk == "finite_outputs":
            n = inv.get("samples", 12)
            bad = None
            for ref in inv.get("sweep", []):
                nm = ref.split(".")[1]
                sv = ir["state"][nm]
                for i in range(n + 1):
                    st = dict(base)
                    st[nm] = sv["min"] + (sv["max"] - sv["min"]) * i / n
                    frame = evaluate(ir, st)
                    for k, v in frame["derived"].items():
                        if isinstance(v, (int, float)) and not math.isfinite(v):
                            bad = f"derived.{k} is not finite at {nm}={st[nm]:g}"
            r.check("invariant.finite_outputs", bad is None, bad or "")

        elif chk == "argmax":
            nm = inv["over"].split(".")[1]
            sv = ir["state"][nm]
            target = inv["of"].split(".")[1]
            best_x, best_v = None, -math.inf
            steps = 900
            for i in range(steps + 1):
                st = dict(base)
                st[nm] = sv["min"] + (sv["max"] - sv["min"]) * i / steps
                v = evaluate(ir, st)["derived"].get(target)
                if v is not None and v > best_v:
                    best_v, best_x = v, st[nm]
            tol = inv.get("tol", 0.5)
            ok = best_x is not None and abs(best_x - inv["expect"]) <= tol
            msg = f"peak at {best_x:.2f} (expected {inv['expect']} ±{tol}), max value {best_v:.2f}"
            r.check(f"invariant.argmax({inv['of']} over {inv['over']})", ok, msg, msg)

        elif chk == "control_affects":
            ctrl = next((c for c in ir["controls"] if c["id"] == inv["control"]), None)
            if not ctrl or not ctrl.get("bind"):
                r.check(f"pedagogy.control_affects({inv['control']})", False, "control not found or unbound")
                continue
            nm = ctrl["bind"].split(".")[1]
            sv = ir["state"][nm]
            target = inv["target"].split(".")[1]
            vals = []
            for i in range(21):
                st = dict(base)
                st[nm] = sv["min"] + (sv["max"] - sv["min"]) * i / 20
                v = evaluate(ir, st)["derived"].get(target)
                if isinstance(v, (int, float)):
                    vals.append(v)
            span = (max(vals) - min(vals)) if vals else 0.0
            denom = max(abs(max(vals)), 1e-9) if vals else 1e-9
            rel = span / denom
            need = inv.get("min_relative_change", 0.05)
            msg = f"relative swing {rel:.2f} (need >= {need})"
            r.check(f"pedagogy.control_affects({inv['control']} -> {inv['target']})", rel >= need, msg, msg)


def pedagogical(ir, r):
    """The learning outcome must be reachable: at least one unlocked state var
    has to be exposed as a control, and at least one probe must be tagged with a
    concept the intent declares."""
    bound = {c["bind"].split(".")[1] for c in ir["controls"] if c.get("bind")}
    unlocked = {k for k, v in ir["state"].items() if not v.get("locked")}
    r.check("pedagogy.controls_exposed", bool(bound & unlocked),
            "no unlocked state variable is exposed as a control")

    concepts = set(ir["intent"]["concept_ids"])
    tagged = {p.get("concept") for p in ir["probes"] if p.get("concept")}
    tagged |= {q.get("concept") for q in ir.get("assessment", []) if q.get("concept")}
    r.check("pedagogy.evidence_tagged", bool(concepts & tagged),
            f"no probe/assessment emits evidence for any of {sorted(concepts)}")


def optional_jsonschema(ir, schema_path, r):
    try:
        import json
        import jsonschema  # noqa
    except Exception:
        r.checks.append(("schema.jsonschema", True, "skipped (jsonschema not installed)"))
        return
    import json
    with open(schema_path) as f:
        schema = json.load(f)
    try:
        jsonschema.validate(ir, schema)
        r.check("schema.jsonschema", True, "")
    except Exception as e:  # pragma: no cover
        r.check("schema.jsonschema", False, str(e).splitlines()[0])


def validate(ir, schema_path=None):
    r = Report()
    structural(ir, r)
    fatal = [c[0] for c in r.checks if not c[1]]
    if "structure.required_keys" not in fatal and "structure.kernel_known" not in fatal:
        referential(ir, r)
        pedagogical(ir, r)
        run_invariants(ir, r)
    if schema_path:
        optional_jsonschema(ir, schema_path, r)
    return r
