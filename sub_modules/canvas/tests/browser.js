#!/usr/bin/env node
/* End-to-end gesture test in a REAL browser.
 *
 *   node tests/browser.js            (needs Chrome; builds out/canvas.html first)
 *
 * A stub DOM cannot do layout, and layout is exactly what this module resolves
 * against — so the honest test drives real PointerEvents against real
 * getBoundingClientRect() output and reads the packets back out. tests/harness.js
 * is the script that gets injected into the built page.
 *
 * Chrome renders the results into the DOM; --dump-dom lets us read them here. */
const fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync, execSync } = require('child_process');

const B = process.argv[2] || path.join(__dirname, '..');
const CHROME = process.env.CHROME || [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/chromium',
].find(p => fs.existsSync(p));

if (!CHROME) {
  console.log('  SKIP  Chrome not found. Set CHROME=/path/to/chrome to run this test.');
  process.exit(0);
}

const built = path.join(B, 'out', 'canvas.html');
if (!fs.existsSync(built)) {
  console.log('  build out/canvas.html first:  python3 build.py');
  process.exit(1);
}

const html = fs.readFileSync(built, 'utf8')
  .replace('<html lang="en">', '<html lang="en" data-theme="light">')
  .replace('</body>', '<script>\n' + fs.readFileSync(path.join(__dirname, 'harness.js'), 'utf8') + '\n</script>\n</body>');

const tmp = path.join(os.tmpdir(), 'nityam-canvas-test-' + process.pid + '.html');
fs.writeFileSync(tmp, html);

let dom = '';
try {
  dom = execFileSync(CHROME, [
    '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--window-size=1200,900', '--virtual-time-budget=9000', '--dump-dom',
    'file://' + tmp
  ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
} catch (e) {
  dom = (e.stdout || '').toString();
} finally {
  try { fs.unlinkSync(tmp); } catch (e) {}
}

/* pull the results panel back out of the dumped DOM */
const rows = [...dom.matchAll(/>(PASS|FAIL)<\/span>\s*([^<]+)<div[^>]*>([^<]*)</g)];
if (!rows.length) {
  console.log('  FAIL  the harness never reported — the page probably threw on load');
  process.exit(1);
}
let bad = 0;
rows.forEach(m => {
  const [, verdict, label, note] = m;
  if (verdict === 'FAIL') bad++;
  console.log(`  ${verdict}  ${label.trim()}`);
  if (note.trim()) console.log(`        ${note.trim()}`);
});
console.log(`\n  BROWSER TEST: ${bad ? 'FAIL (' + bad + ')' : 'PASS'}  (${rows.length} checks)\n`);
process.exit(bad ? 1 : 0);
