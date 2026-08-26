#!/usr/bin/env python3
"""
Nityam Canvas - end to end.

    CanvasDoc  ->  validate  ->  inline runtime  ->  out/canvas.html

The notebook the tutor and the student share. Highlight or circle anything and
the page tells you what you just pointed at, semantically.

Usage
    python3 build.py                 # build out/canvas.html
    python3 build.py --open          # build and open it
    python3 build.py --doc examples/other_notebook.json

Every stage prints. Python 3 only, no pip install, no network at render.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "generate"))

from validate import validate  # noqa: E402

# The canvas runtime, plus the artifact_generator runtime so that an `artifact`
# block can call Nityam.mountArtifact() directly. One namespace, two modules.
CANVAS_RUNTIME = ["anchors.js", "resolve.js", "blocks.js", "annotate.js", "pager.js", "mount.js"]
ARTIFACT_RUNTIME = ["kernel.js", "evaluate.js", "probes.js", "render.js", "mount.js"]

ARTIFACT_DIR = os.path.normpath(os.path.join(HERE, "..", "artifact_generator"))

DIM, BOLD, GREEN, RED, RESET = "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[0m"


def artifact_component_css():
    """Lift the artifact's COMPONENT rules out of its own shell.

    Its token blocks (:root, the two dark blocks) and its body rules are dropped:
    inside a shadow root the tokens already inherit from the notebook's :root,
    which uses the same names by design, and `body` means nothing there.
    What is left is exactly the component styling, which the shadow root
    encapsulates so the two stylesheets cannot reach each other."""
    shell = os.path.join(ARTIFACT_DIR, "shell", "template.html")
    if not os.path.exists(shell):
        return ""
    with open(shell) as f:
        html = f.read()
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    if not m:
        return ""
    css = m.group(1)

    start = css.find("*{box-sizing")          # component rules begin here
    if start < 0:
        return ""
    css = css[start:]
    css = re.sub(r"html,body\{[^}]*\}", "", css)
    css = re.sub(r"\bbody\{[^}]*\}", "", css)

    # Media queries inside a shadow root still measure the VIEWPORT, so the
    # artifact's own responsive rules never fire when it is embedded in a
    # 760px notebook page. Restack it explicitly for this context.
    embed = (
        ":host{display:block;font:15px/1.55 -apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Inter,Roboto,sans-serif;color:var(--ink);"
        "-webkit-font-smoothing:antialiased}\n"
        ".nty-artifact-host .wrap{max-width:none;padding:16px 18px 22px}\n"
        ".nty-artifact-host .grid{grid-template-columns:minmax(0,1fr)}\n"
        ".nty-artifact-host .side{flex-direction:row;align-items:stretch;gap:12px}\n"
        ".nty-artifact-host .side>.card{flex:1;min-width:0}\n"
        ".nty-artifact-host canvas{height:300px}\n"
        ".nty-artifact-host .lesson h1{font-size:22px}\n"
    )
    return embed + css


def step(label, detail=""):
    print(f"  {BOLD}{label:<12}{RESET} {DIM}->{RESET} {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=os.path.join(HERE, "examples", "notebook_projectile.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "canvas.html"))
    ap.add_argument("--open", dest="do_open", action="store_true")
    args = ap.parse_args()

    print(f"\n{BOLD}Nityam Canvas{RESET} {DIM}(proof of concept){RESET}\n")

    # 1 ------------------------------------------------------------- doc
    with open(args.doc) as f:
        doc = json.load(f)
    step("doc", os.path.relpath(args.doc, HERE))
    print(f"               {DIM}{doc.get('title','')} - {len(doc['pages'])} pages, "
          f"{sum(len(p['blocks']) for p in doc['pages'])} blocks{RESET}")

    # 2 -------------------------------------------------------- validate
    schema_path = os.path.join(HERE, "doc", "schema.json")
    art_examples = os.path.join(ARTIFACT_DIR, "examples")
    report = validate(doc, schema_path, art_examples if os.path.isdir(art_examples) else None)
    passed = sum(1 for _, ok, _ in report.checks if ok)
    step("validate", f"{passed}/{len(report.checks)} checks")
    for name, ok, detail in report.checks:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"               {mark}  {name}" + (f"  {DIM}{detail}{RESET}" if detail else ""))

    if not report.ok:
        print(f"\n{RED}  Notebook REJECTED - not rendered.{RESET}")
        print(f"{DIM}  An anchor that never resolves is worse than no anchor: the page{RESET}")
        print(f"{DIM}  looks right and the tutor silently learns nothing.{RESET}\n")
        for e in report.errors:
            print(f"    - {e}")
        print()
        return 1

    # 3 -------------------------------------------------------- artifacts
    artifacts = {}
    wanted = [b["artifact_ir"] for p in doc["pages"] for b in p["blocks"]
              if b["type"] == "artifact" and b.get("artifact_ir")]
    for name in wanted:
        path = os.path.join(art_examples, name)
        with open(path) as f:
            artifacts[name] = json.load(f)
    themes = {}
    tp = os.path.join(art_examples, "themes.json")
    if os.path.exists(tp):
        with open(tp) as f:
            themes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    if wanted:
        step("artifacts", f"{len(artifacts)} bundled from ../artifact_generator  {DIM}{wanted}{RESET}")

    # 4 ----------------------------------------------------------- render
    js = []
    for fn in ARTIFACT_RUNTIME:
        p = os.path.join(ARTIFACT_DIR, "runtime", fn)
        if os.path.exists(p):
            with open(p) as f:
                js.append(f"/* ---- artifact_generator/runtime/{fn} ---- */\n" + f.read())
    for fn in CANVAS_RUNTIME:
        with open(os.path.join(HERE, "runtime", fn)) as f:
            js.append(f"/* ---- canvas/runtime/{fn} ---- */\n" + f.read())
    runtime_js = "\n\n".join(js)
    art_css = artifact_component_css() if artifacts else ""
    if artifacts:
        step("artifact css", f"{len(art_css)//1024} KB lifted from its shell  {DIM}(mounted in a shadow root){RESET}")

    with open(os.path.join(HERE, "shell", "template.html")) as f:
        html = f.read()

    build_meta = {"doc": os.path.basename(args.doc),
                  "checks_passed": passed, "checks_total": len(report.checks)}

    html = (html
            .replace("__TITLE__", doc.get("title", doc["notebook_id"]) + " - Nityam notebook")
            .replace("__RUNTIME_JS__", runtime_js)
            .replace("__DOC_JSON__", json.dumps(doc, ensure_ascii=False))
            .replace("__ARTIFACTS_JSON__", json.dumps(artifacts, ensure_ascii=False))
            .replace("__THEMES_JSON__", json.dumps(themes, ensure_ascii=False))
            .replace("__ARTIFACT_CSS__", json.dumps(art_css))
            .replace("__BUILD_JSON__", json.dumps(build_meta)))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(args.out) / 1024
    step("render", f"{os.path.relpath(args.out, HERE)}  {DIM}({size:.0f} KB, self-contained, no network){RESET}")

    n_anchors = sum(
        len(b.get("anchors", [])) + len([t for t in b.get("terms", []) if not t.get("plain")])
        + len(b.get("regions", []))
        for p in doc["pages"] for b in p["blocks"])
    step("anchors", f"{n_anchors} declared in the doc  {DIM}(the runtime adds one per artifact and work area){RESET}")

    print(f"\n  {GREEN}Done.{RESET}  open {args.out}\n")

    if args.do_open:
        import subprocess
        subprocess.run(["open", args.out], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
