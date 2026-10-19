"""Modal fluid baking; capture explicit frames, not the bounded scrub history."""
import bpy
from ..analyzer.motion import fluid

class AUDVIS_OT_motionFluidBake(bpy.types.Operator):
    bl_idname = 'audvis.motion_fluid_bake'
    bl_label = 'Bake Fluid'
    bl_description = 'Simulate every scene frame and save a particle cache for exact rendering'
    _timer = None

    def invoke(self, context, event):
        if context.object is None or context.object.audvis.scatter.style != 'fluid': return {'CANCELLED'}
        if not bpy.data.filepath:
            self.report({'WARNING'}, 'Save the blend file before baking relative caches')
            return {'CANCELLED'}
        s = context.object.audvis.scatter
        if not s.enable or not context.scene.audvis.motion_enable:
            self.report({'ERROR'}, 'Enable Scatter and Motion FX before baking')
            return {'CANCELLED'}
        self._scene, self._object = context.scene.name, context.object.name
        self._return = context.scene.frame_current
        self._frame, self._end = context.scene.frame_start, context.scene.frame_end
        self._old = s.fluid_use_bake
        s.fluid_use_bake = False
        self._streams = {}
        bpy.audvis._get_motion_engine().invalidate()
        bpy.audvis._get_motion_engine().audio.reset()
        if context.screen.is_animation_playing: bpy.ops.screen.animation_cancel(restore_frame=False)
        self._timer = context.window_manager.event_timer_add(.001, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context, success):
        obj, scene = bpy.data.objects.get(self._object), bpy.data.scenes.get(self._scene)
        if obj is not None: obj.audvis.scatter.fluid_use_bake = True if success else self._old
        context.window_manager.event_timer_remove(self._timer)
        if context.workspace: context.workspace.status_text_set(None)
        if scene is not None: scene.frame_set(self._return)

    def modal(self, context, event):
        obj, scene = bpy.data.objects.get(self._object), bpy.data.scenes.get(self._scene)
        if event.type == 'ESC' or obj is None or scene is None or context.scene != scene:
            self.finish(context, False)
            return {'CANCELLED'}
        if event.type != 'TIMER': return {'PASS_THROUGH'}
        try:
            bpy.audvis.last_scene_frame = None
            scene.frame_set(self._frame)
            bpy.audvis.update_data(scene)
            engine = bpy.audvis._get_motion_engine()
            found = False
            for key, (_, cache) in engine._cache.items():
                if key[:2] != ('scatter', obj.name) or 'flow' not in cache: continue
                flow = cache['flow']
                # Old GP drawings in the engine cache must not receive frames while inactive.
                if flow.frame != self._frame: continue
                name = cache.get('bake_key', 'mesh')
                stream = self._streams.setdefault(name, {'fingerprint': fluid.fingerprint(cache['rest'], cache['pieces']), 'frames': {}})
                stream['frames'][self._frame] = (flow.pos.copy(), flow.rot.copy())
                found = True
            if not found: raise ValueError('No prepared fluid pieces found at this frame')
            context.workspace.status_text_set(f'AudVis: Baking Fluid frame {self._frame} / {self._end}')
            if self._frame == self._end:
                relative = '//audvis_cache/' + bpy.path.clean_name(obj.name) + '_fluid.npz'
                fluid.save_bake(bpy.path.abspath(relative), self._streams)
                obj.audvis.scatter.fluid_bake_path = relative
                self.finish(context, True)
                return {'FINISHED'}
            self._frame += 1
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            self.finish(context, False)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

class AUDVIS_OT_motionFluidClear(bpy.types.Operator):
    bl_idname = 'audvis.motion_fluid_clear'
    bl_label = 'Clear Bake'
    bl_description = 'Detach the particle cache and resume simulation; keep the cache file on disk'
    def execute(self, context):
        if context.object is None: return {'CANCELLED'}
        s = context.object.audvis.scatter
        s.fluid_use_bake = False
        s.fluid_bake_path = ''
        bpy.audvis._get_motion_engine().invalidate()
        return {'FINISHED'}

classes = [AUDVIS_OT_motionFluidBake, AUDVIS_OT_motionFluidClear]
