"""IR -> self-contained HTML. Extracted from build.py so both the CLI and
the ADK ArtifactAgent tool (sub_modules/tutor/app/agents/artifact_agent.py)
call the same rendering logic instead of duplicating it.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RUNTIME_ORDER = ["kernel.js", "evaluate.js", "probes.js", "render.js", "mount.js"]


def render_html(ir: dict, theme_key: str, build_meta: dict) -> str:
    from kernel_py import parity_vectors  # sibling module in generate/

    with open(os.path.join(ROOT, "examples", "themes.json")) as f:
        themes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    if theme_key not in themes:
        theme_key = "plain"
    build_meta = {**build_meta, "theme": theme_key}

    runtime = []
    for fn in RUNTIME_ORDER:
        with open(os.path.join(ROOT, "runtime", fn)) as f:
            runtime.append(f"/* ---- {fn} ---- */\n" + f.read())
    runtime_js = "\n\n".join(runtime)

    with open(os.path.join(ROOT, "shell", "template.html")) as f:
        html = f.read()

    return (
        html
        .replace("__TITLE__", ir["intent"].get("student_prompt", ir["artifact_id"])
                  .replace("{{theme.object}}", "it").replace("{{theme.protagonist}}", "they"))
        .replace("__ARTIFACT_ID__", ir["artifact_id"])
        .replace("__RUNTIME_JS__", runtime_js)
        .replace("__IR_JSON__", json.dumps(ir, ensure_ascii=False))
        .replace("__THEMES_JSON__", json.dumps(themes, ensure_ascii=False))
        .replace("__PARITY_JSON__", json.dumps(parity_vectors()))
        .replace("__BUILD_JSON__", json.dumps(build_meta))
    )
