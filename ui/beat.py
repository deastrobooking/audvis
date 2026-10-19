"""Scene beat runtime and readouts. No per-frame RNA writes."""
import time
import bpy
from bpy.app.handlers import persistent
from ..analyzer.beat import BeatTracker
from .buttonspanel import AudVisButtonsPanel_Npanel

_trackers = {}
_readouts = {}
_switches = {}
_sources = {}

def tracker(scene):
    key = scene.as_pointer()
    if key not in _trackers:
        _trackers[key] = BeatTracker()
    return _trackers[key]

def update(scene):
    p = scene.audvis
    key = scene.as_pointer()
    source = (p.beat_source, p.realtime_enable)
    if _sources.get(key) != source:
        _trackers[key] = BeatTracker()
        _sources[key] = source
    t = tracker(scene)
    now = time.monotonic() if p.beat_source != 'audio' or p.realtime_enable else (scene.frame_current_final-scene.frame_start) / (scene.render.fps/scene.render.fps_base)
    if p.beat_source == 'audio':
        edges = [20 * (1000 ** (i/16)) for i in range(17)]
        energies = [bpy.audvis.driver(edges[i], edges[i+1]) for i in range(16)]
        t.update(now, energies, p.beat_sensitivity, p.beat_bpm_min, max(p.beat_bpm_min, p.beat_bpm_max))
    elif p.beat_source == 'midi':
        a = bpy.audvis.get_midi_realtime_analyzer(scene) if p.midi_realtime.enable else None
        clock = a.clock_state() if a else None
        bpm = a.clock_bpm() if a else None
        t.update(now, tempo=bpm, running=bool(clock and clock.running and bpm))
        if clock is not None and bpm:
            beats = max(0, (clock.count-1)/24 + ((now-clock.ticks[-1])*bpm/60 if clock.running else 0))
            t.counter = int(beats)
            t.phase = beats % 1
            t.bar = beats % 4 / 4
            t.pulse = float(clock.running and t.phase < .15)
    else:
        t.update(now, tempo=t.bpm)
    return t

def tap(scene):
    scene.audvis.beat_source = 'tap'
    key = scene.as_pointer()
    _sources[key] = ('tap', scene.audvis.realtime_enable)
    tracker(scene).tap(time.monotonic())

class AUDVIS_OT_beatTap(bpy.types.Operator):
    bl_idname = 'audvis.beat_tap'
    bl_label = 'Tap Tempo'
    def execute(self, context):
        tap(context.scene)
        return {'FINISHED'}

class AUDVIS_PT_beatNpanel(AudVisButtonsPanel_Npanel):
    bl_label = 'Beat'
    def draw(self, context):
        p = context.scene.audvis
        self.layout.prop(p, 'beat_source')
        t = tracker(context.scene)
        self.layout.label(text=f'{t.bpm:.1f} BPM')
        row = self.layout.row()
        for i in range(4):
            row.label(text=str(i+1), icon='RADIOBUT_ON' if t.counter % 4 == i and t.pulse else 'RADIOBUT_OFF')
        self.layout.operator('audvis.beat_tap')
        self.layout.prop(p, 'beat_sensitivity')
        self.layout.prop(p, 'beat_bpm_min')
        self.layout.prop(p, 'beat_bpm_max')
        self.layout.prop(p, 'realtime_switch_bars')

def meters():
    scene = bpy.context.scene
    if scene is not None:
        p = scene.audvis
        if p.beat_source in {'tap', 'midi'}:
            update(scene)
        t = tracker(scene)
        value = (round(t.bpm, 1), t.counter % 4, t.pulse)
        if _readouts.get(scene.as_pointer()) != value:
            _readouts[scene.as_pointer()] = value
            for w in bpy.context.window_manager.windows:
                for a in w.screen.areas:
                    a.tag_redraw()
    return .05

@persistent
def clear_runtime(_dummy=None):
    _trackers.clear()
    _readouts.clear()
    _switches.clear()
    _sources.clear()


def register():
    if clear_runtime not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(clear_runtime)
    if not bpy.app.timers.is_registered(meters):
        bpy.app.timers.register(meters, persistent=True)

def unregister():
    if clear_runtime in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_runtime)
    if bpy.app.timers.is_registered(meters): bpy.app.timers.unregister(meters)
    _trackers.clear()
    _readouts.clear()
    _switches.clear()
    _sources.clear()

classes = [AUDVIS_OT_beatTap, AUDVIS_PT_beatNpanel]
