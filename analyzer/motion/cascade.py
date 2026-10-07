"""Cascade: a chain of copies where each copy is the previous one moved, rotated
and scaled by one step. The steps compound, so small rotations give spirals and
scale < 1 gives a tunnel/fractal look. Sound stretches the steps per copy - with
the "delay" spread a wave travels down the chain."""
import colorsys

from mathutils import Euler, Matrix, Vector

from .lib import clamp01, elements, place, scene_time

MIN_SCALE = 1e-4


def step_matrix(settings, v):
    loc = Vector(settings.offset) * (1 + settings.audio_offset * v)
    rot = Euler([a * (1 + settings.audio_rotation * v) for a in settings.rotation], 'XYZ')
    scale = Matrix.Diagonal((*settings.scale_step, 1.0))
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ scale


def matrices(base, settings, values):
    """World matrices for copies 1..len(values); copy 0 is the source itself."""
    count = len(values)
    reveal = clamp01(settings.reveal + settings.audio_reveal * (values[0] if values else 0))
    out = []
    m = base.copy()
    for i, v in enumerate(values):
        m = m @ step_matrix(settings, v)
        pulse = max(MIN_SCALE, 1 + settings.audio_scale * v)
        visible = max(MIN_SCALE, clamp01(reveal * count - i))
        out.append(m @ Matrix.Scale(pulse * visible, 4))
    return out


def update(engine, obj, scene, frame):
    settings = obj.audvis.cascade
    copies = elements(settings.collection, exclude=obj)
    if not copies:
        return
    values = engine.audio.values(("cascade", obj.name), settings.audio, engine.driver,
                                 len(copies), scene, frame)
    t = scene_time(scene, frame)
    for i, (copy, matrix) in enumerate(zip(copies, matrices(obj.matrix_world, settings, values))):
        place(copy, matrix, frame, settings.is_baking)
        if settings.use_color:
            hue = (settings.hue + settings.hue_step * (i + 1) + settings.hue_speed * t
                   + settings.audio_hue * values[i]) % 1.0
            copy.color = (*colorsys.hsv_to_rgb(hue, settings.saturation, 1.0), 1.0)
