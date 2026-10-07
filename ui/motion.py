import bmesh
import bpy
from bpy.types import Operator

from ..analyzer.motion import scatter
from ..analyzer.motion.lib import INDEX_KEY
from . import ui_lib
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


def scatter_enable_update(self, context):
    obj = self.id_data
    if obj.type == 'MESH':
        if self.enable:
            refresh(self, context)
        else:
            scatter.restore(obj.data)


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
    obj.audvis.cascade.collection = None
    obj.audvis.orbit.collection = None


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
    """Remove copies created by AudVis (never the user's own objects)."""
    coll = settings.collection
    if coll is None:
        return
    for obj in [o for o in coll.objects if INDEX_KEY in o]:
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
        remove_generated(settings)
        coll = _ensure_collection(settings, obj, "Cascade", context)
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
        temp = None
        if source is None:
            source = temp = _default_satellite()
        make_copies(source, settings.count, coll, True, center.name + " satellite")
        if temp is not None:
            bpy.data.objects.remove(temp)
        settings.enable = True
        orbit_sphere_update(settings, context)
        context.scene.audvis.motion_enable = True
        refresh(context=context)
        return {'FINISHED'}


class AUDVIS_OT_motionClear(Operator):
    """Delete the generated copies"""
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
    """Tear the mesh into pieces and enable Scatter. The original mesh is kept, so it can be restored"""
    bl_idname = "audvis.motion_scatter_prepare"
    bl_label = "Prepare Scatter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = _active(context)
        settings = obj.audvis.scatter
        if obj.data.shape_keys is not None:
            self.report({'ERROR'}, "Scatter moves the vertices directly - remove the shape keys first")
            return {'CANCELLED'}
        settings.enable = False
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
        settings.prepared_mode = settings.piece_mode
        settings.prepared_id += 1
        settings.enable = True
        context.scene.audvis.motion_enable = True
        refresh(context=context)
        return {'FINISHED'}


class AUDVIS_OT_motionScatterRemove(Operator):
    """Put the original mesh back"""
    bl_idname = "audvis.motion_scatter_remove"
    bl_label = "Restore Original Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        return obj is not None and obj.type == 'MESH' and obj.audvis.scatter.original_mesh is not None

    def execute(self, context):
        obj = _active(context)
        settings = obj.audvis.scatter
        settings.enable = False
        old = obj.data
        obj.data = settings.original_mesh
        obj.data.use_fake_user = False
        settings.original_mesh = None
        settings.prepared_mode = ""
        if old.users == 0:
            bpy.data.meshes.remove(old)
        return {'FINISHED'}


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
        box.prop(props, "freq_start")
        box.prop(props, "freq_width")
        if spread and props.spread == 'bands':
            box.prop(props, "freq_step")
    box.prop(props, "factor")
    row = box.row(align=True)
    row.prop(props, "attack")
    row.prop(props, "release")
    if props.source == 'midi':
        ui_lib.generators_ui_midi(_Layout(box), context, props.midi)
    else:
        ui_lib.generators_ui_sequence(_Layout(box), context, props)


class _Layout:
    """ui_lib helpers draw into self.layout"""

    def __init__(self, layout):
        self.layout = layout


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
        col = layout.column(align=True)
        col.prop(s, "count")
        col.prop(s, "linked")
        row = col.row(align=True)
        row.operator("audvis.motion_cascade_generate",
                     text="Regenerate" if s.collection else "Generate", icon='MOD_ARRAY')
        row.operator("audvis.motion_clear", text="", icon='TRASH').effect = 'cascade'
        col.prop(s, "collection")

        col = layout.column(align=True)
        col.label(text="Step per Copy")
        col.prop(s, "offset")
        col.prop(s, "rotation")
        col.prop(s, "scale_step")
        col = layout.column(align=True)
        col.prop(s, "reveal")

        layout.label(text="Sound")
        draw_audio(layout, context, s.audio)
        col = layout.column(align=True)
        col.prop(s, "audio_offset")
        col.prop(s, "audio_rotation")
        col.prop(s, "audio_scale")
        col.prop(s, "audio_reveal")

        col = layout.column(align=True)
        col.prop(s, "use_color")
        if s.use_color:
            col.prop(s, "hue")
            col.prop(s, "hue_step")
            col.prop(s, "hue_speed")
            col.prop(s, "saturation")
            col.prop(s, "audio_hue")
        _draw_bake(layout, s, 'cascade')


class AUDVIS_PT_motionScatterNpanel(_MotionSubpanel):
    bl_label = "Scatter"
    effect = 'scatter'

    @classmethod
    def poll(cls, context):
        obj = _active(context)
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        obj = _active(context)
        s = obj.audvis.scatter
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "piece_mode")
        prepared = scatter.is_prepared(obj.data)
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
        col.prop(s, "stagger")
        col.prop(s, "stagger_mode")
        col.prop(s, "stagger_invert")

        layout.label(text="Sound")
        draw_audio(layout, context, s.audio)
        col = layout.column(align=True)
        if s.audio.spread != 'same':
            col.prop(s, "audio_elements")
        col.prop(s, "audio_amount")


class AUDVIS_PT_motionOrbitNpanel(_MotionSubpanel):
    bl_label = "Orbit / Gravity"
    effect = 'orbit'

    def draw(self, context):
        s = _active(context).audvis.orbit
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Active object is the center")
        col.prop(s, "source_object")
        col.prop(s, "count")
        row = col.row(align=True)
        row.operator("audvis.motion_orbit_populate",
                     text="Repopulate" if s.collection else "Populate", icon='PHYSICS')
        row.operator("audvis.motion_clear", text="", icon='TRASH').effect = 'orbit'
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
        _draw_bake(layout, s, 'orbit')


def _draw_bake(layout, settings, effect):
    col = layout.column(align=True)
    if settings.is_baking:
        col.label(text="Baking, press ESC to cancel")
    else:
        col.operator("audvis.motion_bake", icon='KEYFRAME').effect = effect


classes = [
    AUDVIS_OT_motionCascadeGenerate,
    AUDVIS_OT_motionOrbitPopulate,
    AUDVIS_OT_motionClear,
    AUDVIS_OT_motionScatterPrepare,
    AUDVIS_OT_motionScatterRemove,
    AUDVIS_OT_motionBake,
    AUDVIS_PT_motionNpanel,
    AUDVIS_PT_motionCascadeNpanel,
    AUDVIS_PT_motionScatterNpanel,
    AUDVIS_PT_motionOrbitNpanel,
]
