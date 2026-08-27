"""
kinematics2d - the trusted physics.

This is the Python twin of runtime/kernel.js. It exists so the validator can
SWEEP the model (hundreds of evaluations) before a student ever sees the
artifact. The two implementations are kept honest by a parity check: build.py
samples this one, embeds the vectors in the page, and the JS kernel re-computes
them at load time.

The LLM never writes this file. That is the entire point of the IR approach.
"""

import math

N_PATH_SAMPLES = 90


def kinematics2d(speed: float, angle: float, gravity: float = 9.8, y0: float = 0.0) -> dict:
    """Closed-form 2D projectile motion, no drag.

    speed   launch speed          (m/s)
    angle   launch angle          (degrees, converted here - the IR speaks degrees)
    gravity                       (m/s^2)
    y0      launch height         (m)
    """
    rad = math.radians(angle)
    ux = speed * math.cos(rad)
    uy = speed * math.sin(rad)

    # time to return to y = 0, from y0 with initial vertical velocity uy
    disc = uy * uy + 2.0 * gravity * y0
    tof = (uy + math.sqrt(max(disc, 0.0))) / gravity if gravity > 0 else 0.0

    rng = ux * tof
    max_height = y0 + (uy * uy) / (2.0 * gravity) if uy > 0 else y0

    path = []
    for i in range(N_PATH_SAMPLES + 1):
        t = tof * i / N_PATH_SAMPLES
        path.append({
            "t": t,
            "x": ux * t,
            "y": y0 + uy * t - 0.5 * gravity * t * t,
            "vx": ux,
            "vy": uy - gravity * t,
        })

    return {
        "ux": ux,
        "uy": uy,
        "range": rng,
        "max_height": max_height,
        "time_of_flight": tof,
        "path": path,
        "launch_point": {"x": 0.0, "y": y0},
    }


# ─────────────────────────────────────────────────────────────────────────────
# More of the Class 11 syllabus.
#
# Every kernel returns `path` as a list of {t, x, y, vx, vy} that the renderer
# plots as (x, y). For kernels whose natural picture is a graph against time —
# oscillations, superposition — x IS the time axis and y is the quantity. That
# is a deliberate convention, not an accident: it means one hand-written
# renderer draws every topic, and a new chapter costs a function rather than a
# drawing surface.
# ─────────────────────────────────────────────────────────────────────────────


def shm1d(amplitude: float, mass: float, k: float, phase: float = 0.0) -> dict:
    """Simple harmonic motion — a mass on a spring (NCERT XI, Ch 14).

    amplitude  (m)          mass (kg)          k  spring constant (N/m)
    phase      (degrees)

    The point worth discovering: the period does not depend on the amplitude.
    Pull it twice as far and it still takes the same time to come back.
    """
    k = max(k, 1e-9)
    mass = max(mass, 1e-9)
    omega = math.sqrt(k / mass)
    period = 2.0 * math.pi / omega
    phi = math.radians(phase)

    total_energy = 0.5 * k * amplitude * amplitude
    max_speed = amplitude * omega
    max_accel = amplitude * omega * omega

    path = []
    for i in range(N_PATH_SAMPLES + 1):
        t = period * i / N_PATH_SAMPLES
        x = amplitude * math.cos(omega * t + phi)
        v = -amplitude * omega * math.sin(omega * t + phi)
        path.append({"t": t, "x": t, "y": x, "vx": 1.0, "vy": v})

    return {
        "omega": omega,
        "period": period,
        "frequency": 1.0 / period,
        "max_speed": max_speed,
        "max_accel": max_accel,
        "total_energy": total_energy,
        "path": path,
        "launch_point": {"x": 0.0, "y": amplitude * math.cos(phi)},
    }


def circular2d(radius: float, speed: float) -> dict:
    """Uniform circular motion (NCERT XI, Ch 4).

    radius (m)   speed (m/s)

    Speed is constant and the velocity is not: the direction changes every
    instant, which is what the acceleration is for. The acceleration points at
    the centre — the common wrong answer is that it points outward.
    """
    radius = max(radius, 1e-9)
    speed = max(speed, 0.0)
    omega = speed / radius
    period = (2.0 * math.pi / omega) if omega > 0 else 0.0
    centripetal = speed * speed / radius

    path = []
    for i in range(N_PATH_SAMPLES + 1):
        theta = 2.0 * math.pi * i / N_PATH_SAMPLES
        path.append({
            "t": (period * i / N_PATH_SAMPLES) if period else 0.0,
            "x": radius * math.cos(theta),
            "y": radius * math.sin(theta),
            "vx": -speed * math.sin(theta),
            "vy": speed * math.cos(theta),
        })

    return {
        "omega": omega,
        "period": period,
        "frequency": (1.0 / period) if period else 0.0,
        "centripetal_accel": centripetal,
        "path": path,
        "launch_point": {"x": radius, "y": 0.0},
    }


def incline2d(angle: float, mu: float, mass: float = 1.0, gravity: float = 9.8) -> dict:
    """A block on a rough incline (NCERT XI, Ch 5).

    angle (degrees)   mu  coefficient of friction   mass (kg)   gravity (m/s^2)

    It slides only once tan(angle) exceeds mu, and the mass cancels out of that
    condition entirely — which is the thing students do not believe until they
    have changed the mass and watched nothing happen.
    """
    rad = math.radians(angle)
    weight = mass * gravity
    along = weight * math.sin(rad)
    normal = weight * math.cos(rad)
    friction_max = mu * normal

    slides = along > friction_max
    accel = gravity * (math.sin(rad) - mu * math.cos(rad)) if slides else 0.0
    accel = max(accel, 0.0)
    critical_angle = math.degrees(math.atan(mu))

    # Two seconds of travel down the slope, in world coordinates.
    duration = 2.0
    path = []
    for i in range(N_PATH_SAMPLES + 1):
        t = duration * i / N_PATH_SAMPLES
        d = 0.5 * accel * t * t
        v = accel * t
        path.append({
            "t": t,
            "x": d * math.cos(rad),
            "y": -d * math.sin(rad),
            "vx": v * math.cos(rad),
            "vy": -v * math.sin(rad),
        })

    return {
        "along_slope": along,
        "normal_force": normal,
        "friction_max": friction_max,
        "slides": 1.0 if slides else 0.0,
        "acceleration": accel,
        "critical_angle": critical_angle,
        "path": path,
        "launch_point": {"x": 0.0, "y": 0.0},
    }


def superposition1d(amplitude: float, f1: float, f2: float, duration: float = 1.0) -> dict:
    """Two waves added together (NCERT XI, Ch 15).

    amplitude (m)   f1, f2 frequencies (Hz)   duration (s)

    When the two frequencies are close the sum swells and fades at their
    difference — beats. Waves pass through each other; they do not collide.
    """
    duration = max(duration, 1e-6)
    beat = abs(f1 - f2)

    path, path_a, path_b = [], [], []
    samples = N_PATH_SAMPLES * 4  # a wave needs more points than an arc
    for i in range(samples + 1):
        t = duration * i / samples
        a = amplitude * math.sin(2.0 * math.pi * f1 * t)
        b = amplitude * math.sin(2.0 * math.pi * f2 * t)
        path_a.append({"t": t, "x": t, "y": a, "vx": 1.0, "vy": 0.0})
        path_b.append({"t": t, "x": t, "y": b, "vx": 1.0, "vy": 0.0})
        path.append({"t": t, "x": t, "y": a + b, "vx": 1.0, "vy": 0.0})

    return {
        "beat_frequency": beat,
        "beat_period": (1.0 / beat) if beat > 0 else 0.0,
        "max_amplitude": 2.0 * amplitude,
        "path": path,
        "path_a": path_a,
        "path_b": path_b,
        "launch_point": {"x": 0.0, "y": 0.0},
    }


KERNELS = {
    "kinematics2d": kinematics2d,
    "shm1d": shm1d,
    "circular2d": circular2d,
    "incline2d": incline2d,
    "superposition1d": superposition1d,
}

# Which state variables each kernel port will accept, for referential checks.
KERNEL_PORTS = {
    "kinematics2d": ["speed", "angle", "gravity", "y0"],
    "shm1d": ["amplitude", "mass", "k", "phase"],
    "circular2d": ["radius", "speed"],
    "incline2d": ["angle", "mu", "mass", "gravity"],
    "superposition1d": ["amplitude", "f1", "f2", "duration"],
}

# Scalar outputs a `derived` entry is allowed to reference as kernel.<name>.
KERNEL_OUTPUTS = {
    "kinematics2d": ["ux", "uy", "range", "max_height", "time_of_flight", "path", "launch_point"],
    "shm1d": ["omega", "period", "frequency", "max_speed", "max_accel", "total_energy",
              "path", "launch_point"],
    "circular2d": ["omega", "period", "frequency", "centripetal_accel", "path", "launch_point"],
    "incline2d": ["along_slope", "normal_force", "friction_max", "slides", "acceleration",
                  "critical_angle", "path", "launch_point"],
    "superposition1d": ["beat_frequency", "beat_period", "max_amplitude",
                        "path", "path_a", "path_b", "launch_point"],
}


def parity_vectors():
    """Sample points the JS kernel must reproduce exactly. Guards against drift."""
    out = []
    for speed, angle, y0 in [(20, 30, 0), (20, 45, 0), (20, 60, 0), (35, 15, 0), (12, 75, 0), (25, 45, 10)]:
        k = kinematics2d(speed, angle, 9.8, y0)
        out.append({
            "in": {"speed": speed, "angle": angle, "gravity": 9.8, "y0": y0},
            "out": {
                "ux": k["ux"], "uy": k["uy"], "range": k["range"],
                "max_height": k["max_height"], "time_of_flight": k["time_of_flight"],
            },
        })
    return out
