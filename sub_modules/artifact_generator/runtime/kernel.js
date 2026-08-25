/* kinematics2d - the trusted physics (JS twin of generate/kernel_py.py).
 *
 * Hand-written. Never generated. The IR chooses a kernel; it does not author one.
 * Kept in sync with the Python twin by the parity vectors embedded at build time. */
(function (NS) {
  var N = 90;

  function kinematics2d(inp) {
    var speed = inp.speed, angleDeg = inp.angle;
    var g = inp.gravity == null ? 9.8 : inp.gravity;
    var y0 = inp.y0 == null ? 0 : inp.y0;

    var rad = angleDeg * Math.PI / 180;
    var ux = speed * Math.cos(rad);
    var uy = speed * Math.sin(rad);

    var disc = uy * uy + 2 * g * y0;
    var tof = g > 0 ? (uy + Math.sqrt(Math.max(disc, 0))) / g : 0;

    var range = ux * tof;
    var maxHeight = uy > 0 ? y0 + (uy * uy) / (2 * g) : y0;

    var path = new Array(N + 1);
    for (var i = 0; i <= N; i++) {
      var t = tof * i / N;
      path[i] = { t: t, x: ux * t, y: y0 + uy * t - 0.5 * g * t * t, vx: ux, vy: uy - g * t };
    }

    return {
      ux: ux, uy: uy,
      range: range,
      max_height: maxHeight,
      time_of_flight: tof,
      path: path,
      launch_point: { x: 0, y: y0 }
    };
  }

  NS.KERNELS = { kinematics2d: kinematics2d };
})(window.Nityam = window.Nityam || {});
