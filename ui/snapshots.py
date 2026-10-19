"""Parameter snapshots. Morph jobs keep paths and numbers, never RNA references."""
import time
import bpy
from bpy.app.handlers import persistent
from .midi import mapping
from .buttonspanel import AudVisButtonsPanel_Npanel

_jobs = {}

def capture(scene, snapshot):
    from .motion import scene_effects
    paths = {mapping.full_path_of(scene, 'audvis.motion_master')}
    for obj, effect in scene_effects(scene, include_idle=True):
        paths.add(mapping.full_path_of(obj, 'audvis.' + effect + '.influence'))
        if effect == 'scatter': paths.add(mapping.full_path_of(obj, 'audvis.scatter.amount'))
    for i in range(1, 9): paths.add(mapping.full_path_of(scene, f'audvis.eq_band_{i}.gain'))
    paths.update(m.full_path for m in scene.audvis.midi_realtime.maps if m.target == 'property')
    values = []
    for path in sorted(paths):
        try:
            kind, name, data, index = mapping.parse(path)
            target = mapping._target(getattr(bpy.data, kind)[name], data, index)
            values.append((path, target.read()))
        except (ValueError, KeyError, TypeError): pass
    snapshot.values.clear()
    for path, value in values:
        item = snapshot.values.add()
        item.full_path, item.value = path, value

def recall(scene, name):
    snapshot = scene.audvis.snapshots.get(name)
    if snapshot is None: return False
    values = []
    for item in snapshot.values:
        try:
            kind, idname, data, index = mapping.parse(item.full_path)
            target = mapping._target(getattr(bpy.data, kind)[idname], data, index)
            values.append((item.full_path, target.read(), item.value))
        except (ValueError, KeyError, TypeError): pass
    _jobs[scene.name] = (time.monotonic(), scene.audvis.motion_fade_time, values)
    tick()
    return True

def tick():
    for scene_name, (start, duration, values) in list(_jobs.items()):
        if bpy.data.scenes.get(scene_name) is None:
            _jobs.pop(scene_name, None)
            continue
        factor = min(1, max(0, (time.monotonic()-start)/duration)) if duration > 0 else 1
        for path, before, after in values:
            try:
                kind, name, data, index = mapping.parse(path)
                target = mapping._target(getattr(bpy.data, kind)[name], data, index)
                if factor < 1 and target.rna is not None and target.rna.type in {'BOOLEAN', 'ENUM'}: continue
                target.write(before + (after-before)*factor)
                mapping.written.add((target.idb.as_pointer(), data, index))
            except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, ReferenceError): pass
        if factor >= 1: _jobs.pop(scene_name, None)
    return 1/60

class AUDVIS_OT_snapshot(bpy.types.Operator):
    bl_idname = 'audvis.snapshot'
    bl_label = 'Snapshot'
    bl_options = {'UNDO'}
    action: bpy.props.EnumProperty(items=[('capture', 'Capture', ''), ('update', 'Update', ''), ('delete', 'Delete', ''), ('recall', 'Recall', '')])
    snapshot_name: bpy.props.StringProperty(name="Snapshot")
    def execute(self, context):
        scene = context.scene
        p = scene.audvis
        if self.action == 'capture':
            s = p.snapshots.add()
            names = {p.snapshots[j].name for j in range(len(p.snapshots)-1)}
            i = 1
            while f'Look {i}' in names: i += 1
            s.name = f'Look {i}'
            capture(scene, s)
            p.snapshots_index = len(p.snapshots)-1
        elif self.action == 'recall':
            if not recall(scene, self.snapshot_name): return {'CANCELLED'}
        elif 0 <= p.snapshots_index < len(p.snapshots):
            if self.action == 'update': capture(scene, p.snapshots[p.snapshots_index])
            else:
                p.snapshots.remove(p.snapshots_index)
                p.snapshots_index = max(0, min(p.snapshots_index, len(p.snapshots)-1))
        return {'FINISHED'}

class AUDVIS_UL_snapshots(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False)
        op = layout.operator('audvis.snapshot', text='Recall', icon='PLAY')
        op.action, op.snapshot_name = 'recall', item.name

class AUDVIS_PT_snapshotsNpanel(AudVisButtonsPanel_Npanel):
    bl_label = 'Snapshots'
    def draw(self, context):
        p = context.scene.audvis
        self.layout.template_list('AUDVIS_UL_snapshots', '', p, 'snapshots', p, 'snapshots_index')
        row = self.layout.row()
        for action in ('capture', 'update', 'delete'):
            row.operator('audvis.snapshot', text=action.title()).action = action
        self.layout.prop(p, 'motion_fade_time', text='Morph Time')

@persistent
def clear_runtime(_dummy=None):
    _jobs.clear()


def register():
    if clear_runtime not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(clear_runtime)
    if not bpy.app.timers.is_registered(tick): bpy.app.timers.register(tick, persistent=True)

def unregister():
    if clear_runtime in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_runtime)
    if bpy.app.timers.is_registered(tick): bpy.app.timers.unregister(tick)
    _jobs.clear()

classes = [AUDVIS_OT_snapshot, AUDVIS_UL_snapshots, AUDVIS_PT_snapshotsNpanel]
