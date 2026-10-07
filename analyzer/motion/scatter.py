"""Scatter: tear a mesh apart into pieces (faces, loose parts or single vertices),
fly them out and put them back together. Amount 0 is the untouched mesh, amount 1
fully scattered. The rest positions and piece ids are kept as mesh attributes, so
the effect is a pure function of the amount and time - it can be scrubbed."""
import math

import numpy as np

REST = "audvis_rest"
PIECE = "audvis_piece"
MIN_SCALE = 1e-4


def _read(collection, attr, n, width, dtype=np.float32):
    arr = np.empty(n * width, dtype=dtype)
    collection.foreach_get(attr, arr)
    return arr.reshape(n, width) if width > 1 else arr


def islands(mesh):
    """Connected-component id per vertex (label propagation with pointer jumping)."""
    n = len(mesh.vertices)
    labels = np.arange(n)
    if not len(mesh.edges):
        return labels
    edges = _read(mesh.edges, "vertices", len(mesh.edges), 2, np.int32)
    a, b = edges[:, 0], edges[:, 1]
    while True:
        new = labels.copy()
        low = np.minimum(labels[a], labels[b])
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new = new[new]
        if np.array_equal(new, labels):
            break
        labels = new
    return np.unique(labels, return_inverse=True)[1]


def is_prepared(mesh):
    return mesh is not None and REST in mesh.attributes and PIECE in mesh.attributes


def prepare(mesh, mode):
    """Split the mesh (for 'faces') and store rest positions + piece ids."""
    import bmesh
    if mode == 'faces':
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.split_edges(bm, edges=bm.edges[:])
        bm.to_mesh(mesh)
        bm.free()
    n = len(mesh.vertices)
    pieces = np.arange(n) if mode == 'vertices' else islands(mesh)
    for name in (REST, PIECE):
        if name in mesh.attributes:
            mesh.attributes.remove(mesh.attributes[name])
    mesh.attributes.new(REST, 'FLOAT_VECTOR', 'POINT').data.foreach_set(
        "vector", _read(mesh.vertices, "co", n, 3).ravel())
    mesh.attributes.new(PIECE, 'INT', 'POINT').data.foreach_set("value", pieces.astype(np.int32))
    mesh.update()


def build_cache(mesh, seed):
    n = len(mesh.vertices)
    rest = _read(mesh.attributes[REST].data, "vector", n, 3).astype(np.float64)
    pieces = _read(mesh.attributes[PIECE].data, "value", n, 1, np.int32)
    count = int(pieces.max()) + 1 if n else 0
    sizes = np.maximum(np.bincount(pieces, minlength=count), 1)[:, None]
    centers = np.stack([np.bincount(pieces, rest[:, k], count) for k in range(3)], axis=1) / sizes

    # Piece normals from the rest shape (current vertex normals may be scattered).
    normals = np.zeros((count, 3))
    if len(mesh.polygons):
        starts = _read(mesh.polygons, "loop_start", len(mesh.polygons), 1, np.int32)
        totals = _read(mesh.polygons, "loop_total", len(mesh.polygons), 1, np.int32)
        loops = _read(mesh.loops, "vertex_index", len(mesh.loops), 1, np.int32)
        ok = totals >= 3
        v0, v1, v2 = (loops[starts[ok] + k] for k in range(3))
        face_n = np.cross(rest[v1] - rest[v0], rest[v2] - rest[v0])
        np.add.at(normals, pieces[v0], face_n)

    rng = np.random.default_rng(seed)
    random_dir = rng.normal(size=(count, 3))
    axis = rng.normal(size=(count, 3))
    outward = centers.copy()
    for arr, fallback in ((random_dir, None), (axis, None), (outward, random_dir), (normals, outward)):
        length = np.linalg.norm(arr, axis=1, keepdims=True)
        if fallback is not None:
            arr[:] = np.where(length > 1e-9, arr, fallback)
            length = np.linalg.norm(arr, axis=1, keepdims=True)
        arr /= np.maximum(length, 1e-9)

    dist = np.linalg.norm(centers, axis=1)
    z = centers[:, 2] if count else np.zeros(0)
    return {
        "n": n,
        "rest": rest,
        "pieces": pieces,
        "centers": centers,
        "dirs": {"outward": outward, "normal": normals, "random": random_dir},
        "axis": axis,
        "jitter": rng.random(count) * 2 - 1,
        "spin": rng.random(count) * 2 - 1,
        "phase": rng.random((count, 3)),
        "order": {
            "distance": dist / max(dist.max(), 1e-9) if count else dist,
            "z": (z - z.min()) / max(np.ptp(z), 1e-9) if count else z,
            "random": rng.random(count),
        },
        "at_rest": False,
    }


def _rotate(vectors, axis, angle):
    """Rodrigues rotation of each vector around its own unit axis."""
    cos = np.cos(angle)[:, None]
    sin = np.sin(angle)[:, None]
    dot = np.sum(axis * vectors, axis=1, keepdims=True)
    return vectors * cos + np.cross(axis, vectors) * sin + axis * dot * (1 - cos)


def piece_order(settings, cache):
    order = cache["order"][settings.stagger_mode]
    return 1 - order if settings.stagger_invert else order


def compute(settings, cache, values, t):
    """New vertex positions, or None if every piece is at rest."""
    order = piece_order(settings, cache)
    values = np.asarray(values, dtype=float)
    band = np.minimum((order * len(values)).astype(int), len(values) - 1)
    amount = np.clip(settings.amount + settings.audio_amount * values[band], 0, 1)
    if settings.stagger > 0:
        amount = np.clip(amount * (1 + settings.stagger) - order * settings.stagger, 0, 1)
    ease = amount * amount * (3 - 2 * amount)
    if not ease.any():
        return None

    if settings.direction == 'vector':
        vec = np.array(settings.direction_vector, dtype=float)
        dirs = np.broadcast_to(vec / max(np.linalg.norm(vec), 1e-9), cache["centers"].shape)
    else:
        dirs = cache["dirs"][settings.direction]
    if settings.direction_random > 0:
        dirs = dirs + (cache["dirs"]["random"] - dirs) * settings.direction_random
        dirs = dirs / np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-9)

    distance = settings.distance * (1 + settings.distance_random * cache["jitter"])
    offset = dirs * (distance * ease)[:, None]
    if settings.turbulence > 0:
        wave = np.sin(2 * math.pi * (settings.turbulence_speed * t + cache["phase"]))
        offset += wave * (settings.turbulence * ease)[:, None]
    angle = cache["spin"] * ease * (math.radians(settings.rotation)
                                     + 2 * math.pi * settings.tumble_speed * t)
    scale = np.maximum(MIN_SCALE, 1 - settings.shrink * ease)

    pieces = cache["pieces"]
    centers = cache["centers"][pieces]
    rel = _rotate(cache["rest"] - centers, cache["axis"][pieces], angle[pieces])
    return centers + rel * scale[pieces][:, None] + offset[pieces]


def write(mesh, co):
    mesh.vertices.foreach_set("co", co.astype(np.float32).ravel())
    mesh.update()


def update(engine, obj, scene, frame):
    from .lib import scene_time
    settings = obj.audvis.scatter
    mesh = obj.data
    if not is_prepared(mesh):
        return
    key = ("scatter", obj.name)
    cache = engine.cached(key, (mesh.name, len(mesh.vertices), settings.seed, settings.prepared_id),
                          lambda: build_cache(mesh, settings.seed))
    count = settings.audio_elements if settings.audio.spread != 'same' else 1
    values = engine.audio.values(key, settings.audio, engine.driver, count, scene, frame)
    co = compute(settings, cache, values, scene_time(scene, frame))
    if co is None:
        if not cache["at_rest"]:
            write(mesh, cache["rest"])
            cache["at_rest"] = True
        return
    cache["at_rest"] = False
    write(mesh, co)


def restore(mesh):
    if is_prepared(mesh):
        n = len(mesh.vertices)
        write(mesh, _read(mesh.attributes[REST].data, "vector", n, 3))
