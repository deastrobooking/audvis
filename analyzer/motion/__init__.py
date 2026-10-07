import traceback

from . import cascade, orbit, scatter
from .audio import MotionAudio


class MotionEngine:
    """Runs the Motion FX (cascade, scatter, orbit) of every object once per frame."""

    def __init__(self, driver, cc_reader=None):
        self.driver = driver
        self.cc_reader = cc_reader  # (control, channel) -> 0..1 or None
        self.audio = MotionAudio(self)
        self._cache = {}
        self._reported = set()

    def cached(self, key, signature, build):
        entry = self._cache.get(key)
        if entry is None or entry[0] != signature:
            entry = (signature, build())
            self._cache[key] = entry
        return entry[1]

    def invalidate(self, key=None):
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def on_pre_frame(self, scene, frame):
        if not scene.audvis.motion_enable:
            return
        frame = scene.frame_current_final
        for obj in scene.objects:
            props = obj.audvis
            if props.cascade.enable:
                self._run(cascade.update, obj, scene, frame)
            if props.orbit.enable:
                self._run(orbit.update, obj, scene, frame)
            if props.scatter.enable and obj.type in ('MESH', 'GREASEPENCIL'):
                self._run(scatter.update, obj, scene, frame)

    def _run(self, func, obj, scene, frame):
        try:
            func(self, obj, scene, frame)
        except Exception:
            key = (func.__module__, obj.name)
            if key not in self._reported:  # don't flood the console every frame
                self._reported.add(key)
                print("AudVis Motion FX failed for", obj.name)
                traceback.print_exc()
