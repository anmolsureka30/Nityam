/* The physics, in triplicate.
 *
 * The same kernels exist three times: Python (which the validator SWEEPS before
 * a student sees anything), the sub-module's JS, and this app's ported copy.
 * If they drift, the validator certifies one set of physics and the student
 * explores another — and nothing else in the build would notice.
 *
 *   node tests/kernels.mjs
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const GEN = resolve(ROOT, "..", "sub_modules_examples", "artifact_generator");

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "  ok  " : "  FAIL"} ${name}${extra ? " — " + extra : ""}`);
};

if (!existsSync(GEN)) {
  console.log("  artifact_generator not present. Skipping.");
  process.exit(0);
}

// the sub-module's kernels, loaded the way its own shell does
global.window = {};
// eslint-disable-next-line no-eval
eval(readFileSync(resolve(GEN, "runtime/kernel.js"), "utf8"));
const SUB = window.Nityam.KERNELS;

// this app's ported copy, loaded as a module
const MINE = (await import(resolve(ROOT, "src/lib/artifact/index.js"))).default.KERNELS;

const CASES = [
  ["kinematics2d", { speed: 20, angle: 45, gravity: 9.8, y0: 0 }],
  ["kinematics2d", { speed: 25, angle: 60, gravity: 9.8, y0: 10 }],
  ["shm1d", { amplitude: 0.1, mass: 0.5, k: 20, phase: 0 }],
  ["shm1d", { amplitude: 0.4, mass: 2.0, k: 8, phase: 30 }],
  ["circular2d", { radius: 2, speed: 4 }],
  ["circular2d", { radius: 0.5, speed: 12 }],
  ["incline2d", { angle: 20, mu: 0.5, mass: 1, gravity: 9.8 }],
  ["incline2d", { angle: 40, mu: 0.5, mass: 3, gravity: 9.8 }],
  ["superposition1d", { amplitude: 1, f1: 10, f2: 12, duration: 1 }],
  ["superposition1d", { amplitude: 0.5, f1: 220, f2: 224, duration: 0.5 }],
];

const py = JSON.parse(
  execFileSync("python3", ["-c", `
import sys, json
sys.path.insert(0, ${JSON.stringify(resolve(GEN, "generate"))})
import kernel_py as K
out = []
for name, inp in ${JSON.stringify(CASES)}:
    r = K.KERNELS[name](**inp)
    out.append({
        "scalars": {k: v for k, v in r.items() if isinstance(v, (int, float))},
        "points": {k: [[p["x"], p["y"]] for p in v[::30]]
                   for k, v in r.items() if isinstance(v, list)},
    })
print(json.dumps(out))
`], { encoding: "utf8" }),
);

const near = (a, b) => Math.abs(a - b) < 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

const names = [...new Set(CASES.map(([n]) => n))];
check("every Python kernel exists in the sub-module JS",
      names.every((n) => SUB[n]), names.filter((n) => !SUB[n]).join(", ") || `${names.length}`);
check("…and in this app's ported copy",
      names.every((n) => MINE[n]), names.filter((n) => !MINE[n]).join(", ") || `${names.length}`);

for (const [i, [name, inp]] of CASES.entries()) {
  const ref = py[i];
  const bad = [];
  for (const [label, impl] of [["sub-module", SUB[name]], ["ported", MINE[name]]]) {
    if (!impl) { bad.push(`${label} missing`); continue; }
    const got = impl(inp);
    for (const [k, v] of Object.entries(ref.scalars)) {
      if (!near(got[k], v)) bad.push(`${label}.${k}: ${got[k]} vs ${v}`);
    }
    for (const [k, pts] of Object.entries(ref.points)) {
      if (!Array.isArray(got[k])) { bad.push(`${label}.${k} missing`); continue; }
      pts.forEach(([x, y], n) => {
        const p = got[k][n * 30];
        if (!p || !near(p.x, x) || !near(p.y, y)) bad.push(`${label}.${k}[${n * 30}]`);
      });
    }
  }
  check(`${name} ${JSON.stringify(inp).slice(0, 40)}`, bad.length === 0,
        bad.slice(0, 2).join("; "));
}

/* Physics the kernels must actually get right, independent of whether the three
   copies agree with each other — three identical wrong answers is still wrong. */
const shmA = MINE.shm1d({ amplitude: 0.1, mass: 0.5, k: 20, phase: 0 });
const shmB = MINE.shm1d({ amplitude: 0.9, mass: 0.5, k: 20, phase: 0 });
check("shm1d: period does not depend on amplitude", near(shmA.period, shmB.period),
      `${shmA.period.toFixed(6)} vs ${shmB.period.toFixed(6)}`);

const circ = MINE.circular2d({ radius: 2, speed: 4 });
check("circular2d: a = v²/r", near(circ.centripetal_accel, 8), String(circ.centripetal_accel));

const light = MINE.incline2d({ angle: 30, mu: 0.3, mass: 1, gravity: 9.8 });
const heavy = MINE.incline2d({ angle: 30, mu: 0.3, mass: 90, gravity: 9.8 });
check("incline2d: mass cancels out of the acceleration",
      near(light.acceleration, heavy.acceleration));
check("incline2d: it holds below the critical angle and slides above",
      MINE.incline2d({ angle: 20, mu: 0.5, mass: 1, gravity: 9.8 }).slides === 0 &&
      MINE.incline2d({ angle: 40, mu: 0.5, mass: 1, gravity: 9.8 }).slides === 1);

const beats = MINE.superposition1d({ amplitude: 1, f1: 220, f2: 224, duration: 1 });
check("superposition1d: beat frequency is the difference", near(beats.beat_frequency, 4),
      String(beats.beat_frequency));

console.log();
console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
