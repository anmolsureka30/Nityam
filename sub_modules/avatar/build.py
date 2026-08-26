#!/usr/bin/env python3
"""
Nityam Avatar - the tutor's face.

    runtime/*.js  ->  inline  ->  out/avatar.html

    python3 build.py --open

Python 3 only. No pip install, no build step, no network, no model files.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = ["rig.js", "emotions.js", "speech.js", "mount.js"]

DIM, BOLD, GREEN, RESET = "\033[2m", "\033[1m", "\033[32m", "\033[0m"


def step(label, detail=""):
    print(f"  {BOLD}{label:<12}{RESET} {DIM}->{RESET} {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out", "avatar.html"))
    ap.add_argument("--open", dest="do_open", action="store_true")
    args = ap.parse_args()

    print(f"\n{BOLD}Nityam Avatar{RESET} {DIM}(proof of concept){RESET}\n")

    js = []
    for fn in RUNTIME:
        p = os.path.join(HERE, "runtime", fn)
        with open(p) as f:
            src = f.read()
        js.append(f"/* ---- runtime/{fn} ---- */\n" + src)
        step(fn, f"{len(src) // 1024} KB")
    runtime_js = "\n\n".join(js)

    with open(os.path.join(HERE, "shell", "template.html")) as f:
        html = f.read()

    html = (html
            .replace("__TITLE__", "Nityam Avatar")
            .replace("__RUNTIME_JS__", runtime_js)
            .replace("__BUILD_JSON__", json.dumps({"runtime": RUNTIME})))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    step("render", f"{os.path.relpath(args.out, HERE)}  "
                   f"{DIM}({os.path.getsize(args.out) / 1024:.0f} KB, self-contained){RESET}")
    print(f"\n  {GREEN}Done.{RESET}  open {args.out}\n")

    if args.do_open:
        import subprocess
        subprocess.run(["open", args.out], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
