/* One evaluation cycle: state -> frame.
 *
 * Pure and cheap (closed-form kinematics is microseconds), so we just re-run it
 * on every slider tick. No animation loop, no diffing.
 *
 *   frame = { state, kernel, derived, theme }
 *
 * Everything the renderer and the probes read comes out of exactly this object. */
(function (NS) {

  NS.resolveRef = function (ref, ctx) {
    if (typeof ref === 'number') return ref;
    if (typeof ref !== 'string') return undefined;
    var i = ref.indexOf('.');
    if (i < 0) return undefined;
    var ns = ref.slice(0, i), name = ref.slice(i + 1);
    return ctx[ns] ? ctx[ns][name] : undefined;
  };

  NS.defaultState = function (ir) {
    var s = {};
    for (var k in ir.state) s[k] = ir.state[k].value;
    return s;
  };

  NS.evaluate = function (ir, state, theme) {
    var kfn = NS.KERNELS[ir.kernel];
    if (!kfn) throw new Error('unknown kernel: ' + ir.kernel);

    var inputs = {};
    for (var port in ir.kernel_inputs) {
      inputs[port] = NS.resolveRef(ir.kernel_inputs[port], { state: state });
    }
    var kernel = kfn(inputs);

    var derived = {};
    for (var name in ir.derived) {
      derived[name] = NS.resolveRef(ir.derived[name], { state: state, kernel: kernel });
    }

    return { state: state, kernel: kernel, derived: derived, theme: theme };
  };

  /* {{theme.x}} and {{value}} token substitution for labels and copy. */
  NS.fill = function (tpl, theme, value) {
    if (typeof tpl !== 'string') return tpl;
    return tpl
      .replace(/\{\{\s*theme\.([a-zA-Z_]+)\s*\}\}/g, function (_, k) { return theme[k] != null ? theme[k] : ''; })
      .replace(/\{\{\s*value\s*\}\}/g, value != null ? String(value) : '');
  };

})(window.Nityam = window.Nityam || {});
