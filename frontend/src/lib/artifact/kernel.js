/* Copied from sub_modules_examples/artifact_generator/runtime/ with one edit:
 * the IIFE receives the local NS below instead of window.Nityam. */
import { NS } from "./ns.js";

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

  /* ── more of the Class 11 syllabus ──────────────────────────────────────
     Twins of generate/kernel_py.py, kept honest by the parity vectors build.py
     embeds. For kernels whose natural picture is a graph against time, path.x
     IS time and path.y is the quantity — one renderer then draws every topic,
     so a new chapter costs a function rather than a drawing surface. */

  function shm1d(inp) {
    var A = inp.amplitude, m = Math.max(inp.mass, 1e-9), k = Math.max(inp.k, 1e-9);
    var phi = (inp.phase == null ? 0 : inp.phase) * Math.PI / 180;
    var omega = Math.sqrt(k / m);
    var period = 2 * Math.PI / omega;

    var path = new Array(N + 1);
    for (var i = 0; i <= N; i++) {
      var t = period * i / N;
      path[i] = {
        t: t, x: t, y: A * Math.cos(omega * t + phi),
        vx: 1, vy: -A * omega * Math.sin(omega * t + phi)
      };
    }
    return {
      omega: omega, period: period, frequency: 1 / period,
      max_speed: A * omega, max_accel: A * omega * omega,
      total_energy: 0.5 * k * A * A,
      path: path,
      launch_point: { x: 0, y: A * Math.cos(phi) }
    };
  }

  function circular2d(inp) {
    var r = Math.max(inp.radius, 1e-9), v = Math.max(inp.speed, 0);
    var omega = v / r;
    var period = omega > 0 ? 2 * Math.PI / omega : 0;

    var path = new Array(N + 1);
    for (var i = 0; i <= N; i++) {
      var th = 2 * Math.PI * i / N;
      path[i] = {
        t: period ? period * i / N : 0,
        x: r * Math.cos(th), y: r * Math.sin(th),
        vx: -v * Math.sin(th), vy: v * Math.cos(th)
      };
    }
    return {
      omega: omega, period: period, frequency: period ? 1 / period : 0,
      centripetal_accel: v * v / r,
      path: path,
      launch_point: { x: r, y: 0 }
    };
  }

  function incline2d(inp) {
    var rad = inp.angle * Math.PI / 180;
    var m = inp.mass == null ? 1 : inp.mass;
    var g = inp.gravity == null ? 9.8 : inp.gravity;
    var mu = inp.mu;

    var weight = m * g;
    var along = weight * Math.sin(rad);
    var normal = weight * Math.cos(rad);
    var frictionMax = mu * normal;
    var slides = along > frictionMax;
    var a = slides ? Math.max(g * (Math.sin(rad) - mu * Math.cos(rad)), 0) : 0;

    var duration = 2, path = new Array(N + 1);
    for (var i = 0; i <= N; i++) {
      var t = duration * i / N, d = 0.5 * a * t * t, v = a * t;
      path[i] = {
        t: t, x: d * Math.cos(rad), y: -d * Math.sin(rad),
        vx: v * Math.cos(rad), vy: -v * Math.sin(rad)
      };
    }
    return {
      along_slope: along, normal_force: normal, friction_max: frictionMax,
      slides: slides ? 1 : 0, acceleration: a,
      critical_angle: Math.atan(mu) * 180 / Math.PI,
      path: path,
      launch_point: { x: 0, y: 0 }
    };
  }

  function superposition1d(inp) {
    var A = inp.amplitude, f1 = inp.f1, f2 = inp.f2;
    var duration = Math.max(inp.duration == null ? 1 : inp.duration, 1e-6);
    var beat = Math.abs(f1 - f2);
    var samples = N * 4;                     // a wave needs more points than an arc

    var path = new Array(samples + 1), pa = new Array(samples + 1), pb = new Array(samples + 1);
    for (var i = 0; i <= samples; i++) {
      var t = duration * i / samples;
      var a = A * Math.sin(2 * Math.PI * f1 * t);
      var b = A * Math.sin(2 * Math.PI * f2 * t);
      pa[i] = { t: t, x: t, y: a, vx: 1, vy: 0 };
      pb[i] = { t: t, x: t, y: b, vx: 1, vy: 0 };
      path[i] = { t: t, x: t, y: a + b, vx: 1, vy: 0 };
    }
    return {
      beat_frequency: beat, beat_period: beat > 0 ? 1 / beat : 0,
      max_amplitude: 2 * A,
      path: path, path_a: pa, path_b: pb,
      launch_point: { x: 0, y: 0 }
    };
  }

  NS.KERNELS = {
    kinematics2d: kinematics2d,
    shm1d: shm1d,
    circular2d: circular2d,
    incline2d: incline2d,
    superposition1d: superposition1d
  };
})(NS);
