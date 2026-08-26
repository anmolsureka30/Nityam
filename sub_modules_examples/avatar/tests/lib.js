/* Load the runtime into ONE shared namespace.
 *
 * Each runtime file ends with `(window.Nityam = window.Nityam || {})` — so the
 * simplest correct loader is to give it a window and let it take exactly the
 * code path the browser takes. (Trying to intercept the `module.exports = {}`
 * fallback does not work: an assignment expression evaluates to the assigned
 * value, so the IIFE would still receive a fresh object per file.) */
const fs = require('fs'), path = require('path');

function loadRuntime(B) {
  const win = { Nityam: {} };
  ['rig.js', 'emotions.js', 'speech.js'].forEach(f => {
    const src = fs.readFileSync(path.join(B, 'runtime', f), 'utf8');
    new Function('window', 'console', 'performance', 'module', 'exports', src)(
      win, console, { now: () => 0 }, undefined, undefined);
  });
  return win.Nityam;
}
module.exports = { loadRuntime };
