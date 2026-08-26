#!/usr/bin/env python3
"""
Nityam ArtifactGenerator - end to end.

    spec  ->  IR  ->  validate  ->  render shell  ->  out/artifact.html

Usage
    python3 build.py                       # golden IR, cricket theme
    python3 build.py --theme spiderman     # same artifact, different student
    python3 build.py --live                # Gemini writes the IR, validator gates it
    python3 build.py --open                # build then open in the browser

The point of this file is that every stage is visible. Nothing is hidden behind
a framework.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "generate"))

from spec import ArtifactSpec                      # noqa: E402
from validate import validate                      # noqa: E402
from kernel_py import parity_vectors               # noqa: E402
import generator                                   # noqa: E402
import render                                      # noqa: E402

RUNTIME_ORDER = ["kernel.js", "evaluate.js", "probes.js", "render.js", "mount.js"]

# One kernel, three lessons. This is the point of the IR: none of these needed a
# code change except lesson 3, which introduced the reusable `vector_set` layer.
LESSONS = [
    ("lesson1_max_range.json",       "Maximum range",        "Which angle sends it farthest?"),
    ("lesson2_gravity.json",         "Gravity",              "What if you played on the Moon?"),
    ("lesson3_xy_independence.json", "x/y independence",     "Does it slow down horizontally?"),
]

DIM, BOLD, GREEN, RED, YELLOW, RESET = "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def step(label, detail=""):
    print(f"  {BOLD}{label:<12}{RESET} {DIM}->{RESET} {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=os.path.join(HERE, "examples", "spec_projectile.json"))
    ap.add_argument("--live", action="store_true", help="generate the IR with Gemini instead of using the golden one")
    ap.add_argument("--ir", default=None, help="skip generation and validate this IR file (try examples/ir_broken_physics.json)")
    ap.add_argument("--theme", default=None, help="cricket | spiderman | plain (default: from the spec's student interest)")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "artifact.html"))
    ap.add_argument("--open", dest="do_open", action="store_true")
    ap.add_argument("--all", dest="do_all", action="store_true",
                    help="build all three lessons from the one kernel, plus an index page")
    args = ap.parse_args()

    print(f"\n{BOLD}Nityam ArtifactGenerator{RESET} {DIM}(proof of concept){RESET}\n")

    if args.do_all:
        return build_all(args)
    return main_one(args)


def main_one(args):
    # 1 -------------------------------------------------------------- spec
    spec = ArtifactSpec.load(args.spec)
    step("spec", os.path.relpath(args.spec, HERE))
    print(f"               {DIM}{spec.learning_outcome}{RESET}")

    # 2 ---------------------------------------------------------- generate
    schema_path = os.path.join(HERE, "ir", "schema.json")
    if args.ir:
        with open(args.ir) as f:
            ir = json.load(f)
        source = f"file ({os.path.basename(args.ir)})"
        step("generate", source)
    elif args.live:
        ir, source = generator.generate_live(spec, lambda cand: validate(cand, schema_path))
    else:
        ir, source = generator.generate_mock(spec)
        step("generate", source)

    # 3 ---------------------------------------------------------- validate
    report = validate(ir, schema_path)
    passed = sum(1 for _, ok, _ in report.checks if ok)
    step("validate", f"{passed}/{len(report.checks)} checks")
    for name, ok, detail in report.checks:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"               {mark}  {name}" + (f"  {DIM}{detail}{RESET}" if detail else ""))

    if not report.ok:
        print(f"\n{RED}  Artifact REJECTED - not rendered.{RESET}")
        print(f"{DIM}  A student never sees an artifact that fails the gate.{RESET}\n")
        for e in report.errors:
            print(f"    - {e}")
        print()
        return 1

    # 4-5 --------------------------------------------------- theme + render
    theme_key = args.theme or spec.interest
    step("theme", f"{theme_key}  {DIM}(resolved at render, not baked into the IR){RESET}")
    build_meta = {
        "source": source,
        "checks_passed": passed,
        "checks_total": len(report.checks),
        "spec": os.path.basename(args.spec),
    }
    html = render.render_html(ir, theme_key, build_meta)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    # also drop the IR next to it, so you can read what was actually generated
    ir_out = os.path.join(os.path.dirname(args.out), "artifact_ir.json")
    with open(ir_out, "w", encoding="utf-8") as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)

    # parity vectors, so tests/smoke.js can check the JS kernel against this one
    with open(os.path.join(os.path.dirname(args.out), "parity.json"), "w") as f:
        json.dump(parity_vectors(), f)

    size = os.path.getsize(args.out) / 1024
    step("render", f"{os.path.relpath(args.out, HERE)}  {DIM}({size:.0f} KB, self-contained, no network){RESET}")
    step("ir", os.path.relpath(ir_out, HERE))

    print(f"\n  {GREEN}Done.{RESET}  open {args.out}\n")

    if args.do_open:
        import subprocess
        subprocess.run(["open", args.out], check=False)
    return 0


def build_all(args):
    """Build all three lessons plus an index, to show one kernel serving many lessons."""
    import copy
    out_dir = os.path.dirname(args.out)
    os.makedirs(out_dir, exist_ok=True)
    built = []

    for fname, short, blurb in LESSONS:
        sub = copy.copy(args)
        sub.ir = os.path.join(HERE, "examples", fname)
        sub.out = os.path.join(out_dir, fname.replace(".json", ".html"))
        sub.do_open = False
        sub.do_all = False
        print(f"{BOLD}── {short}{RESET}")
        rc = main_one(sub)
        if rc:
            return rc
        built.append((os.path.basename(sub.out), short, blurb))
        print()

    cards = "\n".join(
        f'<a class="c" href="{f}"><h2>{t}</h2><p>{b}</p>'
        f'<span>kinematics2d</span></a>' for f, t, b in built)
    index = INDEX_HTML.replace("__CARDS__", cards)
    idx = os.path.join(out_dir, "index.html")
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write(index)
    print(f"  {GREEN}All three built.{RESET}  open {idx}\n")
    if args.do_open:
        import subprocess
        subprocess.run(["open", idx], check=False)
    return 0


INDEX_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>One kernel, three lessons</title>
<style>
:root{color-scheme:light;--page:#f6f5f2;--card:#fff;--ink:#1a1a19;--ink2:#55534e;--ink3:#8a8880;--line:#e7e5e0;--s1:#2a78d6;--s3:#1baf7a}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--page:#121211;--card:#1a1a19;--ink:#f4f3ef;--ink2:#b8b6ae;--ink3:#83817a;--line:#2c2c29;--s1:#3987e5;--s3:#199e70}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;-webkit-font-smoothing:antialiased}
.w{max-width:940px;margin:0 auto;padding:64px 22px}
.dot{width:30px;height:30px;border-radius:9px;background:linear-gradient(140deg,var(--s1),var(--s3));margin-bottom:22px}
h1{font-size:31px;font-weight:660;letter-spacing:-.025em;margin:0 0 10px}
.sub{color:var(--ink2);margin:0 0 40px;max-width:60ch;font-size:16px}
.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}
.c{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);
border-radius:15px;padding:22px;transition:transform .14s,box-shadow .14s,border-color .14s}
.c:hover{transform:translateY(-3px);border-color:var(--s1);box-shadow:0 12px 30px -14px rgba(26,26,25,.3)}
.c h2{font-size:17px;font-weight:620;margin:0 0 7px;letter-spacing:-.012em}
.c p{color:var(--ink2);margin:0 0 16px;font-size:14.5px;min-height:42px}
.c span{font:11px ui-monospace,Menlo,monospace;color:var(--ink3);background:var(--page);
border:1px solid var(--line);border-radius:6px;padding:3px 8px}
.n{margin-top:40px;padding-top:22px;border-top:1px solid var(--line);color:var(--ink3);font-size:13.5px;max-width:64ch}
</style></head><body><div class="w">
<div class="dot"></div>
<h1>One kernel, three lessons</h1>
<p class="sub">All three artifacts below run the same hand-written physics engine and the same
renderer. Everything that differs between them &mdash; the sliders, the visuals, the questions and
above all what the artifact watches the student <em>do</em> &mdash; lives in a JSON document the
tutor writes.</p>
<div class="g">__CARDS__</div>
<p class="n">Lessons 1 and 2 required no code changes at all. Lesson 3 added one reusable
layer type (<code>vector_set</code>, ~30 lines) which every future artifact can now use.</p>
</div></body></html>
"""


if __name__ == "__main__":
    sys.exit(main())
