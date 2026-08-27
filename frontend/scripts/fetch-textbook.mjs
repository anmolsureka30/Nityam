/* Download the NCERT chapters the tutor teaches from.
 *
 *   node scripts/fetch-textbook.mjs
 *
 * Only needed if public/textbook/ is empty — the PDFs are committed so the app
 * works on checkout. Kept because the alternative is a hardcoded list of page
 * numbers in a comment somewhere, and because NCERT reissues chapters.
 *
 * Note the host: ncert.nic.in without the www fails its TLS handshake from some
 * networks; www.ncert.nic.in is the one that answers.
 */
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DIR = resolve(ROOT, "public/textbook");

/* Class XI Physics. The current edition RENUMBERED its chapters — Motion in a
   Plane is 3, not the 4 that older material (and this app's first hardcoded
   page reference) assumed, and keph104 is Laws of Motion. Each is paired with
   the artifact kernel that can explore it. */
const CHAPTERS = [
  { file: "keph103", label: "Ch 3 · Motion in a Plane  (kinematics2d, circular2d)" },
  { file: "keph104", label: "Ch 4 · Laws of Motion     (incline2d)" },
  { file: "keph206", label: "Ch 13 · Oscillations      (shm1d)" },
  { file: "keph207", label: "Ch 14 · Waves             (superposition1d)" },
];

mkdirSync(DIR, { recursive: true });
const force = process.argv.includes("--force");

for (const { file, label } of CHAPTERS) {
  const path = resolve(DIR, `${file}.pdf`);
  if (existsSync(path) && !force) {
    console.log(`  have  ${file}  ${label}`);
    continue;
  }
  const url = `https://www.ncert.nic.in/textbook/pdf/${file}.pdf`;
  process.stdout.write(`  get   ${file}  ${label} … `);
  const res = await fetch(url);
  if (!res.ok) {
    console.log(`FAILED ${res.status}`);
    continue;
  }
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.subarray(0, 4).toString() !== "%PDF") {
    console.log("FAILED — that was not a PDF");
    continue;
  }
  writeFileSync(path, buf);
  console.log(`${Math.round(buf.length / 1024)} KB`);
}

console.log("\nNow rebuild the index:  node scripts/build-textbook-index.mjs");
