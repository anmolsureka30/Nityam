"""
CanvasDoc validation.

Same shape as the artifact generator's validator (see
../artifact_generator/generate/validate.py): mechanical passes that run before
anything reaches a student.

  1. structural  - required keys, known block types, page numbering
  2. referential - anchors resolve: every `span` occurs in its block's text,
                   every diagram selector looks plausible, artifacts are bundled
  3. integrity   - anchor ids unique across the document, image rects in range
  4. grounding   - the pedagogical gate: does this notebook actually have
                   anything to point AT? A page of unanchored prose is a page
                   the tutor cannot have a conversation about.

Zero third-party dependencies; `jsonschema` is used only if it happens to exist.
"""

import os
import re

BLOCK_TYPES = {"tutor_text", "heading", "equation", "diagram", "image",
               "artifact", "callout", "student_work"}
TONES = {"neutral", "prompt", "warning"}
IMAGE_KINDS = {"web", "generated", "photo"}


class Report:
    def __init__(self):
        self.errors = []
        self.checks = []

    def err(self, msg):
        self.errors.append(msg)

    def check(self, name, ok, detail="", info=""):
        """detail = why it failed; info = worth showing even on success."""
        self.checks.append((name, bool(ok), info if ok else detail))
        if not ok:
            self.errors.append(f"{name}: {detail}")

    @property
    def ok(self):
        return not self.errors


def _blocks(doc):
    for page in doc.get("pages", []):
        for b in page.get("blocks", []):
            yield page, b


# ---------------------------------------------------------------- pass 1

def structural(doc, r):
    missing = [k for k in ("doc_version", "notebook_id", "pages") if k not in doc]
    r.check("structure.required_keys", not missing, f"missing {missing}")
    if missing:
        return

    r.check("structure.doc_version", doc["doc_version"] == "0.1", f"got {doc['doc_version']!r}")
    r.check("structure.has_pages", bool(doc["pages"]), "no pages")

    nums = [p.get("page") for p in doc["pages"]]
    r.check("structure.page_numbering", nums == list(range(1, len(nums) + 1)),
            f"pages must be 1..n in order, got {nums}")

    for page, b in _blocks(doc):
        if b.get("type") not in BLOCK_TYPES:
            r.err(f"structure.blocks: unknown type {b.get('type')!r} on page {page.get('page')}")
        if "id" not in b:
            r.err(f"structure.blocks: block on page {page.get('page')} has no id")
        t = b.get("type")
        if t in ("tutor_text", "heading", "callout") and not b.get("text"):
            r.err(f"structure.blocks: {t} '{b.get('id')}' has no text")
        if t == "equation" and not b.get("terms"):
            r.err(f"structure.blocks: equation '{b.get('id')}' has no terms")
        if t == "callout" and b.get("tone") and b["tone"] not in TONES:
            r.err(f"structure.blocks: callout '{b.get('id')}' bad tone {b['tone']!r}")
        if t == "image":
            if not b.get("src"):
                r.err(f"structure.blocks: image '{b.get('id')}' has no src")
            if b.get("kind") and b["kind"] not in IMAGE_KINDS:
                r.err(f"structure.blocks: image '{b.get('id')}' bad kind {b['kind']!r}")


# ---------------------------------------------------------------- pass 2

def referential(doc, r, artifacts_dir=None):
    """The pass that catches an anchor pointing at text that isn't there - which
    would render fine and then silently never resolve."""
    for page, b in _blocks(doc):
        where = f"page {page.get('page')} block '{b.get('id')}'"

        for a in b.get("anchors", []):
            if "id" not in a:
                r.err(f"ref.anchors: anchor without id in {where}")
                continue
            if b.get("type") in ("tutor_text", "callout"):
                if not a.get("span"):
                    r.err(f"ref.anchors: '{a['id']}' in {where} needs a `span`")
                elif a["span"] not in (b.get("text") or ""):
                    r.err(f"ref.anchors: '{a['id']}' span {a['span']!r} does not occur in {where}")
            elif b.get("type") == "diagram":
                if not a.get("element"):
                    r.err(f"ref.anchors: '{a['id']}' in {where} needs an `element` selector")
                else:
                    sel = a["element"]
                    if not sel.startswith("#"):
                        r.err(f"ref.anchors: '{a['id']}' selector {sel!r} should be an #id")
                    elif f'id="{sel[1:]}"' not in (b.get("svg") or ""):
                        r.err(f"ref.anchors: '{a['id']}' selector {sel!r} not present in the svg of {where}")

        for t in b.get("terms", []):
            if "id" not in t or "tex" not in t:
                r.err(f"ref.terms: term in {where} needs id and tex")

        for rg in b.get("regions", []):
            if "id" not in rg or "rect" not in rg:
                r.err(f"ref.regions: region in {where} needs id and rect")
                continue
            rect = rg["rect"]
            if len(rect) != 4 or not all(isinstance(v, (int, float)) for v in rect):
                r.err(f"ref.regions: '{rg['id']}' rect must be 4 numbers")
            elif not (0 <= rect[0] <= 1 and 0 <= rect[1] <= 1
                      and 0 < rect[2] <= 1 and 0 < rect[3] <= 1
                      and rect[0] + rect[2] <= 1.001 and rect[1] + rect[3] <= 1.001):
                r.err(f"ref.regions: '{rg['id']}' rect {rect} is not inside the unit square")

        if b.get("type") == "artifact":
            name = b.get("artifact_ir")
            if not name:
                r.err(f"ref.artifact: {where} has no artifact_ir")
            elif artifacts_dir:
                path = os.path.join(artifacts_dir, name)
                if not os.path.exists(path):
                    r.err(f"ref.artifact: {where} references {name}, which is not in {artifacts_dir}")

    r.check("ref.integrity", not any(e.startswith("ref.") for e in r.errors),
            "some anchors do not resolve")


# ---------------------------------------------------------------- pass 3

def integrity(doc, r):
    seen = {}
    dupes = []
    for page, b in _blocks(doc):
        ids = [a["id"] for a in b.get("anchors", []) if "id" in a]
        ids += [t["id"] for t in b.get("terms", []) if "id" in t and not t.get("plain")]
        ids += [rg["id"] for rg in b.get("regions", []) if "id" in rg]
        for i in ids:
            if i in seen:
                dupes.append(f"{i} (in {seen[i]} and {b.get('id')})")
            seen[i] = b.get("id")
    r.check("integrity.anchor_ids_unique", not dupes, f"duplicates: {dupes}",
            f"{len(seen)} anchors, all unique")

    block_ids = [b.get("id") for _, b in _blocks(doc)]
    bd = [i for i in set(block_ids) if block_ids.count(i) > 1]
    r.check("integrity.block_ids_unique", not bd, f"duplicate block ids: {bd}")


# ---------------------------------------------------------------- pass 4

def grounding(doc, r):
    """The gate that matters. A notebook with no anchors renders perfectly and
    is useless: the student can circle things and the tutor learns nothing."""
    per_page = []
    for p in doc.get("pages", []):
        n = 0
        for b in p.get("blocks", []):
            n += len(b.get("anchors", []))
            n += len([t for t in b.get("terms", []) if not t.get("plain")])
            n += len(b.get("regions", []))
            if b.get("type") in ("artifact", "student_work"):
                n += 1
        per_page.append((p.get("page"), n))

    bare = [pg for pg, n in per_page if n == 0]
    r.check("grounding.every_page_anchored", not bare,
            f"pages with nothing to point at: {bare}",
            f"anchors per page: {[n for _, n in per_page]}")

    concepts = set(doc.get("concepts", []))
    tagged = set()
    for _, b in _blocks(doc):
        for a in b.get("anchors", []):
            if a.get("concept"):
                tagged.add(a["concept"])
        for t in b.get("terms", []):
            if t.get("concept"):
                tagged.add(t["concept"])
        for rg in b.get("regions", []):
            if rg.get("concept"):
                tagged.add(rg["concept"])
    if concepts:
        missing = concepts - tagged
        r.check("grounding.concepts_reachable", not missing,
                f"declared but no anchor carries them: {sorted(missing)}",
                f"{len(tagged & concepts)}/{len(concepts)} declared concepts anchored")


def optional_jsonschema(doc, schema_path, r):
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
        jsonschema.validate(doc, schema)
        r.check("schema.jsonschema", True, "")
    except Exception as e:
        r.check("schema.jsonschema", False, str(e).splitlines()[0])


def validate(doc, schema_path=None, artifacts_dir=None):
    r = Report()
    structural(doc, r)
    fatal = [c[0] for c in r.checks if not c[1]]
    if "structure.required_keys" not in fatal:
        referential(doc, r, artifacts_dir)
        integrity(doc, r)
        grounding(doc, r)
    if schema_path:
        optional_jsonschema(doc, schema_path, r)
    return r
