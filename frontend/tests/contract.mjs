/* Do the frontend's block types and the backend's pydantic models still agree?
 *
 * `NotebookBlock` in src/lib/types.ts and the Block union in
 * backend/app/canvas/doc.py are hand-mirrored, and nothing else checks them
 * against each other. A field added on one side only does not break the
 * typechecker, does not break either test suite, and shows up as a block that
 * renders with a piece missing — or a patch the reducer silently drops.
 *
 * This is not hypothetical: these two files were edited by two people at once,
 * which is exactly when a mirror drifts.
 *
 * The frontend side is read with the TypeScript compiler rather than a regex,
 * so intersections (`BlockCommon & {...}`) resolve properly. The backend side is
 * read out of pydantic's own model_fields.
 *
 *   node tests/contract.mjs
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = resolve(ROOT, "..", "backend");
const PY = resolve(BACKEND, ".venv/bin/python");

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};

if (!existsSync(PY)) {
  console.log("  backend virtualenv not built — run backend/run.sh once. Skipping.");
  process.exit(0);
}

// ────────────────────────────────────────────────── the frontend's view
const ts = createRequire(import.meta.url)("typescript");
const file = resolve(ROOT, "src/lib/types.ts");
const program = ts.createProgram([file], { strict: true, noEmit: true });
const checker = program.getTypeChecker();
const source = program.getSourceFile(file);

const aliasOf = (name) => {
  let found;
  ts.forEachChild(source, (node) => {
    if (ts.isTypeAliasDeclaration(node) && node.name.text === name) found = node;
    if (ts.isInterfaceDeclaration(node) && node.name.text === name) found = node;
  });
  return found;
};

const membersOf = (name) => {
  const decl = aliasOf(name);
  if (!decl) return null;
  const type = checker.getTypeAtLocation(decl.name);
  const variants = type.isUnion?.() ? type.types : [type];
  const out = {};
  for (const v of variants) {
    const props = checker.getPropertiesOfType(v);
    const kindSym = props.find((p) => p.name === "kind");
    const key = kindSym
      ? checker.typeToString(checker.getTypeOfSymbolAtLocation(kindSym, decl.name)).replace(/"/g, "")
      : "_";
    out[key] = props.map((p) => p.name).filter((p) => p !== "kind").sort();
  }
  return out;
};

const frontend = {
  blocks: membersOf("NotebookBlock"),
  anchor: membersOf("Anchor")?._ ?? null,
  checkpoint: membersOf("Checkpoint")?._ ?? null,
  option: membersOf("CheckpointOption")?._ ?? null,
};

// ────────────────────────────────────────────────── the backend's view
const backend = JSON.parse(
  execFileSync(PY, ["-c", `
import json, sys
sys.path.insert(0, ".")
from app.canvas import doc as D

def fields(cls, drop=("kind",)):
    return sorted(f for f in cls.model_fields if f not in drop)

print(json.dumps({
    "blocks": {
        cls.model_fields["kind"].default: fields(cls)
        for cls in (D.Heading, D.TutorText, D.Equation, D.Callout,
                    D.ArtifactBlock, D.Pulled, D.NextUp)
    },
    "anchor": fields(D.Anchor, ()),
    "checkpoint": fields(D.Checkpoint, ()),
    "option": fields(D.CheckpointOption, ()),
    "patches": sorted(
        cls.model_fields["op"].default
        for cls in (D.AppendBlock, D.ReplaceBlock, D.Strike, D.PointAt, D.ShowQuiz, D.Goto)
    ),
}))
`], { cwd: BACKEND, encoding: "utf8" }),
);

// ───────────────────────────────────────────────────────── compare
const kinds = [...new Set([...Object.keys(backend.blocks), ...Object.keys(frontend.blocks ?? {})])].sort();
check("both sides declare the same block kinds",
      kinds.every((k) => backend.blocks[k] && frontend.blocks?.[k]),
      kinds.filter((k) => !backend.blocks[k] || !frontend.blocks?.[k]).join(", ") || `${kinds.length} kinds`);

for (const kind of kinds) {
  const a = new Set(backend.blocks[kind] ?? []);
  const b = new Set(frontend.blocks?.[kind] ?? []);
  const only = (x, y) => [...x].filter((f) => !y.has(f));
  check(`block "${kind}" has the same fields on both sides`,
        only(a, b).length === 0 && only(b, a).length === 0,
        only(a, b).length || only(b, a).length
          ? `backend-only=[${only(a, b)}] frontend-only=[${only(b, a)}]`
          : `${a.size} fields`);
}

for (const [name, fe] of [["Anchor", frontend.anchor], ["Checkpoint", frontend.checkpoint],
                          ["CheckpointOption", frontend.option]]) {
  const be = backend[name === "Anchor" ? "anchor" : name === "Checkpoint" ? "checkpoint" : "option"];
  const a = new Set(be), b = new Set(fe ?? []);
  const only = (x, y) => [...x].filter((f) => !y.has(f));
  check(`${name} matches`,
        !!fe && only(a, b).length === 0 && only(b, a).length === 0,
        !fe ? "not found in types.ts"
            : (only(a, b).length || only(b, a).length
               ? `backend-only=[${only(a, b)}] frontend-only=[${only(b, a)}]`
               : `${a.size} fields`));
}

/* The reducer must handle every op the backend can send: an unhandled one falls
   through the switch and the patch is silently lost. */
const reducerSrc = execFileSync("cat", [resolve(ROOT, "src/lib/notebookReducer.ts")], { encoding: "utf8" });
const missing = backend.patches.filter((op) => !reducerSrc.includes(`case "${op}"`));
check("the reducer handles every patch op the backend can send",
      missing.length === 0,
      missing.length ? `unhandled: ${missing}` : backend.patches.join(", "));

console.log();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
