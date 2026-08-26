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


KERNELS = {"kinematics2d": kinematics2d}

# Which state variables each kernel port will accept, for referential checks.
KERNEL_PORTS = {"kinematics2d": ["speed", "angle", "gravity", "y0"]}

# Scalar outputs a `derived` entry is allowed to reference as kernel.<name>.
KERNEL_OUTPUTS = {
    "kinematics2d": ["ux", "uy", "range", "max_height", "time_of_flight", "path", "launch_point"]
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
