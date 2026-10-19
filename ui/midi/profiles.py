"""Portable, versioned mapping profiles and sequential controller banks."""
import json
import math
import re
import uuid
import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
from . import mapping


def fields(m):
    return {p.identifier: getattr(m, p.identifier) for p in m.bl_rna.properties
            if p.identifier not in {'rna_type', 'uid'} and not p.is_readonly}

def export_profile(scene, path):
    with open(path, 'w', encoding='utf8') as f:
        json.dump({'version': 1, 'mappings': [fields(m) for m in scene.audvis.midi_realtime.maps]}, f, indent=2)

def import_profile(scene, path, replace=False):
    with open(path, encoding='utf8') as f: data = json.load(f)
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('mappings'), list):
        raise ValueError('Unsupported mapping profile')
    # Validate every field before replacing the existing collection.
    from ..props.midi import AudvisMidiMapProperties
    rna = AudvisMidiMapProperties.bl_rna.properties
    for row in data['mappings']:
        if not isinstance(row, dict): raise ValueError('Invalid mapping')
        for key, value in row.items():
            p = rna.get(key)
            if p is None or key in {'rna_type', 'uid'} or p.is_readonly: raise ValueError('Unknown mapping field: ' + key)
            if p.type == 'ENUM' and value not in {i.identifier for i in p.enum_items}: raise ValueError('Invalid ' + key)
            if p.type == 'STRING' and not isinstance(value, str): raise ValueError('Invalid ' + key)
            if p.type == 'BOOLEAN' and not isinstance(value, bool): raise ValueError('Invalid ' + key)
            if p.type in {'INT', 'FLOAT'} and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)): raise ValueError('Invalid ' + key)
            if p.type == 'INT' and not isinstance(value, int): raise ValueError('Invalid integer ' + key)
    maps = scene.audvis.midi_realtime.maps
    if replace:
        for m in maps: mapping.forget(m)
        maps.clear()
    for row in data['mappings']:
        m = maps.add()
        # Data-path callback resets range, so restore response fields afterwards.
        if 'full_path' in row: m.full_path = row['full_path']
        for key, value in row.items():
            if key != 'full_path': setattr(m, key, value)
        m.uid = uuid.uuid4().hex
    scene.audvis.midi_realtime.maps_index = max(0, len(maps)-1)

def fill_bank(scene, index, count):
    maps = scene.audvis.midi_realtime.maps
    if not 0 <= index < len(maps): return 0
    row = fields(maps[index])
    if row['target'] != 'property' or row['kind'] not in {'cc', 'note'}: return 0
    # Increment the last integer in the property path, never one in the ID name.
    path = row['data_path'] + (f"[{row['index']}]" if row['index'] >= 0 else '')
    matches = list(re.finditer(r'\d+', path))
    if not matches: return 0
    match = matches[-1]
    added = 0
    for i in range(1, count):
        if row['number'] + i > 127: break
        changed = path[:match.start()] + str(int(match.group())+i) + path[match.end():]
        collection = getattr(bpy.data, row['id_type'], None)
        idb = collection.get(row['id_name']) if collection is not None else None
        full = mapping.full_path_of(idb, changed)
        try: parsed = mapping.parse(full)
        except ValueError: continue
        m = maps.add()
        m.full_path = full
        for key, value in row.items():
            if key not in {'full_path','data_path','index','id_type','id_name','number'}: setattr(m,key,value)
        m.id_type, m.id_name, m.data_path, m.index = parsed
        m.number = row['number']+i
        m.uid = uuid.uuid4().hex
        added += 1
    return added

class AUDVIS_OT_midiProfileExport(bpy.types.Operator, ExportHelper):
    bl_idname = 'audvis.midi_profile_export'
    bl_label = 'Export Profile'
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})
    def execute(self, context):
        try: export_profile(context.scene, self.filepath)
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}

class AUDVIS_OT_midiProfileImport(bpy.types.Operator, ImportHelper):
    bl_idname = 'audvis.midi_profile_import'
    bl_label = 'Import Profile'
    bl_options = {'UNDO'}
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})
    replace: bpy.props.BoolProperty(name='Replace Existing', default=False, description='Replace all mappings instead of appending')
    def execute(self, context):
        try: import_profile(context.scene, self.filepath, self.replace)
        except (OSError, ValueError, TypeError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}

class AUDVIS_OT_midiFillBank(bpy.types.Operator):
    bl_idname = 'audvis.midi_fill_bank'
    bl_label = 'Fill Bank'
    bl_options = {'UNDO'}
    count: bpy.props.IntProperty(name='Bank Size', default=8, min=2, max=128, description='Total controls including the selected mapping')
    def invoke(self, context, event): return context.window_manager.invoke_props_dialog(self)
    def execute(self, context):
        n = fill_bank(context.scene, context.scene.audvis.midi_realtime.maps_index, self.count)
        self.report({'INFO'}, f'Added {n} mappings; missing targets skipped')
        return {'FINISHED'}

classes = [AUDVIS_OT_midiProfileExport, AUDVIS_OT_midiProfileImport, AUDVIS_OT_midiFillBank]
