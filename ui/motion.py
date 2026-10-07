import time

import bmesh
import bpy
from bpy.types import Operator

from ..analyzer.motion import instances, scatter
from ..analyzer.motion.lib import HELPER_KEY, INDEX_KEY
from . import motion_presets, ui_lib
from .buttonspanel import AudVisButtonsPanel_Npanel

GENERATED_KEY = "audvis_motion_generated"
EFFECTS = ('cascade', 'orbit', 'scatter')


def _engine():
    audvis = getattr(bpy, "audvis", None)
    return audvis._get_motion_engine() if audvis is not None else None


def refresh(self=None, context=None):
    """Re-run the effects on the current frame, so changes show up while paused."""
    context = context or bpy.context
    engine = _engine()
    if engine is not None and context.scene is not None and context.scene.audvis.motion_enable:
        engine.on_pre_frame(context.scene, None)


def scatter_prepared(obj):
    if obj.type == 'MESH':
        return scatter.is_prepared(obj.data)
    return scatter.gp_is_prepared(obj)


def scatter_enable_update(self, context):
    obj = self.id_data
    if self.enable:
        refresh(self, context)
    elif obj.type in ('MESH', 'GREASEPENCIL'):
        scatter.restore(obj)


def orbit_sphere_update(self, context):
    obj = self.id_data
    if self.show_sphere and obj.type == 'EMPTY':
        obj.empty_display_type = 'SPHERE'
        obj.empty_display_size = self.sphere_radius
    refresh(self, context)


def _active(context):
    return context.active_object or context.object


def _reset_motion_props(obj):
    """Copies inherit the source's settings - they must not become sources themselves."""
    for name in EFFECTS:
        getattr(obj.audvis, name).enable = False
    for name in ('cascade', 'orbit'):
        settings = getattr(obj.audvis, name)
        settings.collection = None
        settings.instancer = None


def _ensure_collection(settings, owner, suffix, context):
    coll = settings.collection
    if coll is None:
        coll = bpy.data.collections.new("{} {}".format(owner.name, suffix))
        coll[GENERATED_KEY] = True
        parent = owner.users_collection[0] if owner.users_collection else context.scene.collection
        parent.children.link(coll)
        settings.collection = coll
    return coll


def remove_generated(settings):
    """Remove copies / instancers created by AudVis (never the user's own objects)."""
    coll = settings.collection
    settings.instancer = None
    if coll is None:
        return
    for obj in [o for o in coll.objects if INDEX_KEY in o or HELPER_KEY in o]:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.batch_remove([data])
    if coll.get(GENERATED_KEY) and not coll.objects and not coll.children:
        bpy.data.collections.remove(coll)
        settings.collection = None


def make_copies(source, count, coll, linked, name):
    for i in range(1, count + 1):
        copy = source.copy()
        if not linked and source.data is not None:
            copy.data = source.data.copy()
        copy.animation_data_clear()
        copy.parent = None
        copy.name = "{}.{:03d}".format(name, i)
        _reset_motion_props(copy)
        copy[INDEX_KEY] = i
        coll.objects.link(copy)


def _helper(obj, coll=None):
    """Tag (and link) an object AudVis manages: removed with the copies, never a copy itself."""
    obj[HELPER_KEY] = True
    if coll is not None:
        coll.objects.link(obj)
    return obj


def _default_satellite():
    mesh = bpy.data.meshes.new("AudVis Orbit Satellite")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=.15)
    bm.to_mesh(mesh)
    bm.free()
    return bpy.data.objects.new("AudVis Orbit Satellite", mesh)


class AUDVIS_OT_motionCascadeGenerate(Operator):
    """Create the cascade copies of the active object"""
    bl_idname = "audvis.motion_cascade_generate"
    bl_label = "Generate Cascade"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def execute(self, context):
        obj = _active(context)
        settings = obj.audvis.cascade
        if settings.layout == 'curve' and settings.curve_object is None:
            self.report({'WARNING'}, "Pick a Curve for the 'Along Curve' layout")
        remove_generated(settings)
        coll = _ensure_collection(settings, obj, "Cascade", context)
        if settings.output == 'instances':
            settings.instancer = _helper(instances.create_carrier(obj.name + " cascade instances", obj, coll))
        else:
            make_copies(obj, settings.count, coll, settings.linked, obj.name + " cascade")
        settings.enable = True
        context.scene.audvis.motion_enable = True
        refresh(context=context)
        return {'FINISHED'}


class AUDVIS_OT_motionOrbitPopulate(Operator):
    """Create satellites orbiting the active object"""
    bl_idname = "audvis.motion_orbit_populate"
    bl_label = "Populate Orbit"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def execute(self, context):
        center = _active(context)
        settings = center.audvis.orbit
        source = settings.source_object
        if source == center:
            self.report({'ERROR'}, "The center can't orbit itself")
            return {'CANCELLED'}
        remove_generated(settings)
        coll = _ensure_collection(settings, center, "Orbit", context)
        if settings.output == 'instances':
            if source is None:  # the instanced source has to live somewhere: hidden in the collection
                source = _helper(_default_satellite(), coll)
                source.hide_set(True)
                source.hide_render = True
            settings.instancer = _helper(instances.create_carrier(center.name + " orbit instances", source, coll))
        else:
            temp = None
            if source is None:
                source = temp = _default_satellite()
            make_copies(source, settings.count, coll, True, center.name + " satellite")
            if temp is not None:
                mesh = temp.data
                bpy.data.objects.remove(temp)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        settings.enable = True
        orbit_sphere_update(settings, context)
        context.scene.audvis.motion_enable = True
        refresh(context=context)
        return {'FINISHED'}


class AUDVIS_OT_motionClear(Operator):
    """Delete the generated copies / instancer"""
    bl_idname = "audvis.motion_clear"
    bl_label = "Delete Copies"
    bl_options = {'REGISTER', 'UNDO'}

    effect: bpy.props.EnumProperty(items=[('cascade', "Cascade", ""), ('orbit', "Orbit", "")])

    def execute(self, context):
        obj = _active(context)
        if obj is None:
            return {'CANCELLED'}
        settings = getattr(obj.audvis, self.effect)
        remove_generated(settings)
        settings.enable = False
        return {'FINISHED'}


class AUDVIS_OT_motionScatterPrepare(Operator):
    """Tear the mesh / Grease Pencil into pieces and enable Scatter. The original can be restored"""
    bl_idname = "audvis.motion_scatter_prepare"
    bl_label = "Prepare Scatter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        return obj is not None and (obj.type == 'MESH' or scatter.gp_supported(obj))

    def execute(self, context):
        obj = _active(context)
        settings = obj.audvis.scatter
        settings.enable = False
        if obj.type == 'MESH':
            if obj.data.shape_keys is not None:
                self.report({'ERROR'}, "Scatter moves the vertices directly - remove the shape keys first")
                return {'CANCELLED'}
            self._prepare_mesh(obj, settings)
        else:
            scatter.gp_prepare(obj, settings.piece_mode)
        settings.prepared_mode = settings.piece_mode
        settings.prepared_id += 1
        settings.enable = True
        context.scene.audvis.motion_enable = True
        refresh(context=context)
        return {'FINISHED'}

    @staticmethod
    def _prepare_mesh(obj, settings):
        old = obj.data
        if settings.original_mesh is None:
            original = old.copy()
            original.name = old.name + " (AudVis original)"
            original.use_fake_user = True
            settings.original_mesh = original
            if old.users > 1:  # don't tear apart other objects sharing this mesh
                obj.data = old.copy()
        else:  # prepare again from the untouched original
            obj.data = settings.original_mesh.copy()
            obj.data.use_fake_user = False
            obj.data.name = old.name
            if old.users == 0:
                bpy.data.meshes.remove(old)
        scatter.prepare(obj.data, settings.piece_mode)


class AUDVIS_OT_motionScatterRemove(Operator):
    """Put the original shape back"""
    bl_idname = "audvis.motion_scatter_remove"
    bl_label = "Restore Original"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        if obj is None:
            return False
        if obj.type == 'MESH':
            return obj.audvis.scatter.original_mesh is not None
        return scatter.gp_is_prepared(obj)

    def execute(self, context):
        obj = _active(context)
        settings = obj.audvis.scatter
        settings.enable = False
        settings.prepared_mode = ""
        if obj.type != 'MESH':
            scatter.gp_restore(obj, remove=True)
            return {'FINISHED'}
        old = obj.data
        obj.data = settings.original_mesh
        obj.data.use_fake_user = False
        settings.original_mesh = None
        if old.users == 0:
            bpy.data.meshes.remove(old)
        return {'FINISHED'}


class AUDVIS_OT_motionAddAttractor(Operator):
    """Add an Empty as an attractor of this effect (at the 3D cursor)"""
    bl_idname = "audvis.motion_add_attractor"
    bl_label = "Add Attractor"
    bl_options = {'REGISTER', 'UNDO'}

    effect: bpy.props.EnumProperty(items=[(e, e.title(), "") for e in EFFECTS])

    def execute(self, context):
        owner = _active(context)
        if owner is None:
            return {'CANCELLED'}
        settings = getattr(owner.audvis, self.effect)
        coll = settings.attractors
        if coll is None:
            coll = bpy.data.collections.new(owner.name + " Attractors")
            parent = owner.users_collection[0] if owner.users_collection else context.scene.collection
            parent.children.link(coll)
            settings.attractors = coll
        empty = bpy.data.objects.new("Attractor", None)
        empty.empty_display_type = 'SPHERE'
        empty.location = context.scene.cursor.location
        empty.audvis.attractor.audio.source = 'off'
        empty.audvis.attractor.strength = 0
        coll.objects.link(empty)
        refresh(context=context)
        return {'FINISHED'}


def _cc_owner(obj, effect):
    return getattr(obj.audvis, effect).cc


class AUDVIS_OT_motionLearnCC(Operator):
    """Move a knob / fader on your MIDI controller to assign it (ESC cancels)"""
    bl_idname = "audvis.motion_learn_cc"
    bl_label = "MIDI Learn"

    effect: bpy.props.EnumProperty(items=[(e, e.title(), "") for e in EFFECTS + ('attractor',)])

    _timer = None
    _start_msg = None
    _started = 0.0
    _obj_name = ""

    @classmethod
    def poll(cls, context):
        return _active(context) is not None and context.scene.audvis.midi_realtime.enable

    def _analyzer(self, context):
        if not context.scene.audvis.midi_realtime.enable:
            return None
        return bpy.audvis.get_midi_realtime_analyzer(context.scene)

    def invoke(self, context, event):
        analyzer = self._analyzer(context)
        if analyzer is None:
            self.report({'ERROR'}, "Enable MIDI Realtime first")
            return {'CANCELLED'}
        self._obj_name = _active(context).name
        self._start_msg = analyzer.get_last_msg()
        self._started = time.time()
        _cc_owner(_active(context), self.effect).is_learning = True
        self._timer = context.window_manager.event_timer_add(.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, cc):
        cc.is_learning = False
        context.window_manager.event_timer_remove(self._timer)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

    def modal(self, context, event):
        obj = bpy.data.objects.get(self._obj_name)
        if obj is None:
            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}
        cc = _cc_owner(obj, self.effect)
        if event.type == 'ESC' or time.time() - self._started > 15:
            self._finish(context, cc)
            return {'CANCELLED'}
        if event.type == 'TIMER':
            analyzer = self._analyzer(context)
            if analyzer is None:  # MIDI Realtime switched off / AudVis reloaded while waiting
                self.report({'WARNING'}, "MIDI Realtime stopped - learn cancelled")
                self._finish(context, cc)
                return {'CANCELLED'}
            msg = analyzer.get_last_msg()
            if msg is not None and msg is not self._start_msg and hasattr(msg, "control"):
                cc.control = msg.control
                cc.channel = msg.channel
                cc.enable = True
                self.report({'INFO'}, "Assigned CC {} (channel {})".format(msg.control, msg.channel))
                self._finish(context, cc)
                return {'FINISHED'}
        return {'PASS_THROUGH'}


class AUDVIS_OT_motionBake(Operator):
    """Insert keyframes for every frame of the scene, then disable the live effect"""
    bl_idname = "audvis.motion_bake"
    bl_label = "Bake to Keyframes"

    effect: bpy.props.EnumProperty(items=[('cascade', "Cascade", ""), ('orbit', "Orbit", "")])

    timer = None
    settings = None
    return_frame = cur_frame = end_frame = 0

    @classmethod
    def poll(cls, context):
        return _active(context) is not None and context.scene.audvis.motion_enable

    def invoke(self, context, event):
        self.settings = getattr(_active(context).audvis, self.effect)
        if not self.settings.enable or self.settings.collection is None:
            self.report({'ERROR'}, "Nothing to bake")
            return {'CANCELLED'}
        if self.settings.output == 'instances':
            self.report({'ERROR'}, "Instances can't be baked to keyframes - switch Output to Objects")
            return {'CANCELLED'}
        scene = context.scene
        bpy.ops.screen.animation_cancel()
        self.return_frame = scene.frame_current
        self.cur_frame = scene.frame_start
        self.end_frame = scene.frame_end
        self.settings.is_baking = True
        _engine().audio.reset()
        self.timer = context.window_manager.event_timer_add(.0000001, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        self.settings.is_baking = False
        self.settings.enable = False
        context.scene.frame_set(self.return_frame)
        context.window_manager.event_timer_remove(self.timer)
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        if event.type == 'TIMER':
            context.scene.frame_set(self.cur_frame)  # the engine keyframes while is_baking is set
            start = context.scene.frame_start
            perc = int((self.cur_frame - start) / max(1, self.end_frame - start) * 100)
            context.workspace.status_text_set("AudVis: Baking Motion FX: {}%".format(perc))
            if self.cur_frame >= self.end_frame:
                self._end(context)
                return {'FINISHED'}
            self.cur_frame += 1
            return {'PASS_THROUGH'}
        elif event.type == 'ESC':
            self._end(context)
            return {'FINISHED'}
        return {'PASS_THROUGH'}


# ---------------------------------------------------------------- drawing helpers

class _Layout:
    """ui_lib helpers draw into self.layout"""

    def __init__(self, layout):
        self.layout = layout


def draw_audio(layout, context, props, spread=True):
    box = layout.box().column(align=True)
    box.prop(props, "source")
    if props.source == 'off':
        return
    if spread:
        box.prop(props, "spread")
        if props.spread == 'delay':
            box.prop(props, "delay")
    if props.source == 'midi':
        box.prop(props, "midi_note")
    else:
        box.prop(props, "eq_band")
        if props.eq_band == 'off':
            box.prop(props, "freq_start")
            box.prop(props, "freq_width")
        if spread and props.spread == 'bands':
            box.prop(props, "freq_step")
    box.prop(props, "factor")
    box.prop(props, "response")
    if props.response == 'trigger':
        box.prop(props, "threshold")
        box.prop(props, "trigger_shape")
        row = box.row(align=True)
        row.prop(props, "trigger_length", text="Length")
        row.prop(props, "cooldown", text="Cooldown")
    else:
        row = box.row(align=True)
        row.prop(props, "attack")
        row.prop(props, "release")
    if props.source == 'midi':
        ui_lib.generators_ui_midi(_Layout(box), context, props.midi)
    else:
        if spread:
            box.prop(props, "stereo")
            if props.stereo != 'off' and context.scene.audvis.channels < 2:
                row = box.row()
                row.alert = True
                row.label(text="Set Channels Count to 2+", icon='ERROR')
        ui_lib.generators_ui_sequence(_Layout(box), context, props)


def draw_cc(layout, context, cc, effect):
    box = layout.box().column(align=True)
    row = box.row(align=True)
    row.prop(cc, "enable")
    if cc.is_learning:
        row.label(text="Move a knob...", icon='REC')
    else:
        row.operator("audvis.motion_learn_cc", text="Learn", icon='EYEDROPPER').effect = effect
    if not cc.enable:
        return
    if effect != 'attractor':
        box.prop(cc, "target")
    row = box.row(align=True)
    row.prop(cc, "control")
    row.prop(cc, "channel", text="Ch")
    box.prop(cc, "mode")
    row = box.row(align=True)
    row.prop(cc, "range_min")
    row.prop(cc, "range_max")
    if not context.scene.audvis.midi_realtime.enable:
        box.label(text="Enable MIDI Realtime to receive CC", icon='INFO')


def draw_attractors(layout, settings, effect):
    row = layout.row(align=True)
    row.prop(settings, "attractors")
    row.operator("audvis.motion_add_attractor", text="", icon='ADD').effect = effect


def draw_output(layout, settings):
    layout.prop(settings, "output", expand=True)


def draw_presets(layout, effect):
    layout.menu(motion_presets.menus[effect].bl_idname, icon='PRESET')


def _draw_bake(layout, settings, effect):
    col = layout.column(align=True)
    if settings.output == 'instances':
        return
    if settings.is_baking:
        col.label(text="Baking, press ESC to cancel")
    else:
        col.operator("audvis.motion_bake", icon='KEYFRAME').effect = effect


# ---------------------------------------------------------------- panels

class AUDVIS_PT_motionNpanel(AudVisButtonsPanel_Npanel):
    bl_label = "Motion FX"

    @classmethod
    def poll(cls, context):
        return True

    def draw_header(self, context):
        self.layout.prop(context.scene.audvis, "motion_enable", text="")

    def draw(self, context):
        col = self.layout.column(align=True)
        if not context.scene.audvis.motion_enable:
            col.label(text="Enable Motion FX in the header", icon='INFO')
        obj = _active(context)
        col.label(text=obj.name if obj else "Select an Object", icon='OBJECT_DATA')


class _MotionSubpanel(AudVisButtonsPanel_Npanel):
    bl_parent_id = "AUDVIS_PT_motionNpanel"
    effect = None

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def draw_header(self, context):
        self.layout.prop(getattr(_active(context).audvis, self.effect), "enable", text="")


class AUDVIS_PT_motionCascadeNpanel(_MotionSubpanel):
    bl_label = "Cascade"
    effect = 'cascade'

    def draw(self, context):
        s = _active(context).audvis.cascade
        layout = self.layout
        draw_presets(layout, 'cascade')
        col = layout.column(align=True)
        draw_output(col, s)
        col.prop(s, "count")
        if s.output == 'objects':
            col.prop(s, "linked")
        row = col.row(align=True)
        generated = s.collection or s.instancer
        row.operator("audvis.motion_cascade_generate",
                     text="Regenerate" if generated else "Generate", icon='MOD_ARRAY')
        row.operator("audvis.motion_clear", text="", icon='TRASH').effect = 'cascade'
        if s.output == 'objects':
            col.prop(s, "collection")

        col = layout.column(align=True)
        col.prop(s, "layout")
        if s.layout in ('phyllotaxis', 'grid'):
            col.prop(s, "spacing")
        if s.layout == 'grid':
            row = col.row(align=True)
            row.prop(s, "grid_columns")
            row.prop(s, "grid_rows")
        if s.layout == 'curve':
            col.prop(s, "curve_object")
            col.prop(s, "curve_offset")
        col = layout.column(align=True)
        col.label(text="Step per Copy")
        if s.layout in ('chain', 'phyllotaxis'):
            col.prop(s, "offset")
        col.prop(s, "rotation")
        col.prop(s, "scale_step")
        layout.prop(s, "reveal")

        layout.label(text="Sound")
        draw_audio(layout, context, s.audio)
        col = layout.column(align=True)
        col.prop(s, "audio_offset")
        col.prop(s, "audio_rotation")
        col.prop(s, "audio_scale")
        col.prop(s, "audio_reveal")
        draw_cc(layout, context, s.cc, 'cascade')

        col = layout.column(align=True)
        col.prop(s, "use_color")
        if s.use_color:
            col.prop(s, "hue")
            col.prop(s, "hue_step")
            col.prop(s, "hue_speed")
            col.prop(s, "saturation")
            col.prop(s, "audio_hue")
        draw_attractors(layout, s, 'cascade')
        _draw_bake(layout, s, 'cascade')


class AUDVIS_PT_motionScatterNpanel(_MotionSubpanel):
    bl_label = "Scatter"
    effect = 'scatter'

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        return obj is not None and obj.type in ('MESH', 'GREASEPENCIL')

    def draw(self, context):
        obj = _active(context)
        s = obj.audvis.scatter
        layout = self.layout
        draw_presets(layout, 'scatter')
        col = layout.column(align=True)
        col.prop(s, "piece_mode")
        prepared = scatter_prepared(obj)
        row = col.row(align=True)
        row.operator("audvis.motion_scatter_prepare",
                     text="Tear Apart Again" if prepared else "Tear Apart", icon='MOD_EXPLODE')
        row.operator("audvis.motion_scatter_remove", text="", icon='LOOP_BACK')
        if prepared and s.prepared_mode and s.prepared_mode != s.piece_mode:
            col.label(text="Click Tear Apart Again to apply", icon='ERROR')
        if not prepared:
            return

        col = layout.column(align=True)
        col.prop(s, "amount", slider=True)
        col.prop(s, "seed")
        col = layout.column(align=True)
        col.prop(s, "direction")
        if s.direction == 'vector':
            col.prop(s, "direction_vector")
        col.prop(s, "direction_random", slider=True)
        col.prop(s, "distance")
        col.prop(s, "distance_random", slider=True)
        col = layout.column(align=True)
        col.prop(s, "rotation")
        col.prop(s, "tumble_speed")
        col.prop(s, "shrink", slider=True)
        col.prop(s, "turbulence")
        if s.turbulence > 0:
            col.prop(s, "turbulence_speed")
        col = layout.column(align=True)
        col.prop(s, "orbit_speed")
        if s.orbit_speed != 0:
            col.prop(s, "orbit_tilt")
        col = layout.column(align=True)
        col.prop(s, "stagger")
        col.prop(s, "stagger_mode")
        col.prop(s, "stagger_invert")

        box = layout.box().column(align=True)
        box.label(text="Morph", icon='MOD_SIMPLEDEFORM')
        box.prop(s, "morph_target")
        if s.morph_target is not None:
            box.prop(s, "morph", slider=True)
            box.prop(s, "morph_scatter", slider=True)
            box.prop(s, "morph_scale")
            box.prop(s, "audio_morph")

        layout.label(text="Sound")
        draw_audio(layout, context, s.audio)
        col = layout.column(align=True)
        if s.audio.spread != 'same':
            col.prop(s, "audio_elements")
        col.prop(s, "audio_amount")
        draw_cc(layout, context, s.cc, 'scatter')
        draw_attractors(layout, s, 'scatter')


class AUDVIS_PT_motionOrbitNpanel(_MotionSubpanel):
    bl_label = "Orbit / Gravity"
    effect = 'orbit'

    def draw(self, context):
        s = _active(context).audvis.orbit
        layout = self.layout
        draw_presets(layout, 'orbit')
        col = layout.column(align=True)
        col.label(text="Active object is the center")
        draw_output(col, s)
        col.prop(s, "source_object")
        col.prop(s, "count")
        row = col.row(align=True)
        generated = s.collection or s.instancer
        row.operator("audvis.motion_orbit_populate",
                     text="Repopulate" if generated else "Populate", icon='PHYSICS')
        row.operator("audvis.motion_clear", text="", icon='TRASH').effect = 'orbit'
        if s.output == 'objects':
            col.prop(s, "collection")

        col = layout.column(align=True)
        col.prop(s, "radius_min")
        col.prop(s, "radius_max")
        col.prop(s, "inclination")
        col.prop(s, "speed")
        col.prop(s, "kepler")
        col.prop(s, "seed")
        col = layout.column(align=True)
        col.prop(s, "scale")
        col.prop(s, "scale_random", slider=True)
        col.prop(s, "align")
        if s.align == 'spin':
            col.prop(s, "spin_speed")

        box = layout.box().column(align=True)
        box.label(text="Gravity Sphere", icon='SPHERE')
        box.prop(s, "gravity", slider=True)
        box.prop(s, "gravity_mode")
        box.prop(s, "sphere_radius")
        box.prop(s, "show_sphere")
        box.prop(s, "gravity_stagger")
        if s.gravity_mode == 'shell':
            box.prop(s, "shell_spin")

        layout.label(text="Sound")
        draw_audio(layout, context, s.audio)
        col = layout.column(align=True)
        col.prop(s, "audio_speed")
        col.prop(s, "audio_radius")
        col.prop(s, "audio_gravity")
        draw_cc(layout, context, s.cc, 'orbit')
        draw_attractors(layout, s, 'orbit')
        _draw_bake(layout, s, 'orbit')


class AUDVIS_PT_motionAttractorNpanel(AudVisButtonsPanel_Npanel):
    bl_parent_id = "AUDVIS_PT_motionNpanel"
    bl_label = "Attractor"

    @classmethod
    def poll(cls, context):
        return _active(context) is not None

    def draw(self, context):
        s = _active(context).audvis.attractor
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Used when in an effect's Attractors collection")
        col.prop(s, "mode")
        col.prop(s, "strength")
        if s.mode == 'attract':
            col.prop(s, "sphere_radius")
        elif s.mode == 'repel':
            col.prop(s, "distance")
        else:
            col.prop(s, "twist")
        col.prop(s, "influence")
        layout.label(text="Sound")
        draw_audio(layout, context, s.audio, spread=False)
        if s.audio.source != 'off':
            layout.prop(s, "audio_strength")
        draw_cc(layout, context, s.cc, 'attractor')


classes = motion_presets.classes + [
    AUDVIS_OT_motionCascadeGenerate,
    AUDVIS_OT_motionOrbitPopulate,
    AUDVIS_OT_motionClear,
    AUDVIS_OT_motionScatterPrepare,
    AUDVIS_OT_motionScatterRemove,
    AUDVIS_OT_motionAddAttractor,
    AUDVIS_OT_motionLearnCC,
    AUDVIS_OT_motionBake,
    AUDVIS_PT_motionNpanel,
    AUDVIS_PT_motionCascadeNpanel,
    AUDVIS_PT_motionScatterNpanel,
    AUDVIS_PT_motionOrbitNpanel,
    AUDVIS_PT_motionAttractorNpanel,
]
