"""Orbit + gravity sphere: satellites circle a center object on tilted orbits.
Gravity (keyframed and/or driven by sound) pulls them onto a sphere around the
center - the orbit collapses into a sphere of objects and is released again."""
import math

import numpy as np
from mathutils import Matrix, Quaternion, Vector

from .lib import elements, place, scene_time

MIN_SCALE = 1e-4
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))


def random_params(seed, n):
    rng = np.random.default_rng(seed)
    axes = rng.normal(size=(n, 3))
    axes /= np.maximum(np.linalg.norm(axes, axis=1, keepdims=True), 1e-9)
    return {
        "radius": rng.random(n),
        "phase": rng.random(n),
        "tilt": rng.random(n) * 2 - 1,
        "node": rng.random(n) * 2 * math.pi,
        "scale": rng.random(n) * 2 - 1,
        "spin_phase": rng.random(n),
        "axis": axes,
    }


def fibonacci_sphere(n):
    k = np.arange(n)
    z = 1 - 2 * (k + .5) / max(n, 1)
    r = np.sqrt(np.maximum(0, 1 - z * z))
    theta = GOLDEN_ANGLE * k
    return np.stack([np.cos(theta) * r, np.sin(theta) * r, z], axis=1)


def _orbit_frame(vec_plane, tilt, node):
    """Rotate in-plane vectors (x, y, 0) by the orbit tilt (around X) and node (around Z)."""
    x, y = vec_plane[:, 0], vec_plane[:, 1]
    y_tilted = y * np.cos(tilt)
    z = y * np.sin(tilt)
    return np.stack([x * np.cos(node) - y_tilted * np.sin(node),
                     x * np.sin(node) + y_tilted * np.cos(node),
                     z], axis=1)


def positions(settings, rnd, values, turns, t):
    """Local positions, per-element gravity (eased 0..1) and tangents."""
    n = len(values)
    v = np.asarray(values, dtype=float)
    r_min, r_max = settings.radius_min, max(settings.radius_min, settings.radius_max)
    radius = r_min + (r_max - r_min) * rnd["radius"]
    speed = (r_min / radius) ** 1.5 if settings.kepler else np.ones(n)
    angle = 2 * math.pi * (rnd["phase"] + turns * speed)
    radius_now = radius * np.maximum(0, 1 + settings.audio_radius * v)
    tilt = math.radians(settings.inclination) * rnd["tilt"]
    plane = np.stack([np.cos(angle), np.sin(angle), np.zeros(n)], axis=1)
    pos = _orbit_frame(plane * radius_now[:, None], tilt, rnd["node"])
    tangent = _orbit_frame(np.stack([-np.sin(angle), np.cos(angle), np.zeros(n)], axis=1), tilt, rnd["node"])

    gravity = np.clip(settings.gravity + settings.audio_gravity * v, 0, 1)
    if settings.gravity_stagger > 0:  # outer orbits fall in later
        gravity = np.clip(gravity * (1 + settings.gravity_stagger) - rnd["radius"] * settings.gravity_stagger, 0, 1)
    ease = gravity * gravity * (3 - 2 * gravity)

    if settings.gravity_mode == 'shell':
        spin = 2 * math.pi * settings.shell_spin * t
        shell = fibonacci_sphere(n)
        c, s = math.cos(spin), math.sin(spin)
        target = np.stack([shell[:, 0] * c - shell[:, 1] * s, shell[:, 0] * s + shell[:, 1] * c, shell[:, 2]], axis=1)
        target *= settings.sphere_radius
    elif settings.gravity_mode == 'radial':
        norm = np.maximum(np.linalg.norm(pos, axis=1, keepdims=True), 1e-9)
        target = pos / norm * settings.sphere_radius
    else:  # core
        target = np.zeros((n, 3))
    pos = pos + (target - pos) * ease[:, None]
    return pos, ease, tangent


def update(engine, center, scene, frame):
    settings = center.audvis.orbit
    sats = elements(settings.collection, exclude=center)
    n = len(sats)
    if not n:
        return
    key = ("orbit", center.name)
    rnd = engine.cached(key, (settings.seed, n), lambda: random_params(settings.seed, n))
    values = engine.audio.values(key, settings.audio, engine.driver, n, scene, frame)
    t = scene_time(scene, frame)
    fps = scene.render.fps / scene.render.fps_base
    boost = engine.audio.accumulate(key, settings.audio_speed * sum(values) / n / fps, scene, frame)
    pos, ease, tangent = positions(settings, rnd, values, settings.speed * t + boost, t)

    scales = settings.scale * np.maximum(MIN_SCALE, 1 + settings.scale_random * rnd["scale"])
    if settings.gravity_mode == 'core':
        scales = scales * np.maximum(MIN_SCALE, 1 - ease)
    spin = 2 * math.pi * (rnd["spin_phase"] + settings.spin_speed * t)
    base = center.matrix_world
    for i, sat in enumerate(sats):
        if settings.align == 'spin':
            rot = Quaternion(rnd["axis"][i], spin[i]).to_matrix().to_4x4()
        elif settings.align == 'tangent':
            rot = Vector(tangent[i]).to_track_quat('Y', 'Z').to_matrix().to_4x4()
        else:
            rot = Matrix.Identity(4)
        matrix = base @ Matrix.Translation(pos[i]) @ rot @ Matrix.Scale(scales[i], 4)
        place(sat, matrix, frame, settings.is_baking)
