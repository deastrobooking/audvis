"""Render six Workbench frames per fluid preset into dist/fluid-preview."""
import importlib
import pathlib
import sys
import math
import bpy
from mathutils import Vector
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
p = bpy.context.preferences.addons.new(); p.module = ROOT.name
addon.register()
try:
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,radius=1)
    obj = bpy.context.object
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 72
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'SINGLE'
    scene.display.shading.single_color = (.15,.55,.85)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'
    scene.world.color = (.04,.04,.04)
    bpy.ops.object.camera_add(location=(8,-11,7))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'; camera.data.ortho_scale=10
    scene.camera=camera
    bpy.context.view_layer.objects.active=obj
    engine = bpy.audvis._get_motion_engine()
    engine.driver = lambda *a,**kw: 5*(.5+.5*math.sin(scene.frame_current*.5))
    folder = ROOT/'dist/fluid-preview'; folder.mkdir(parents=True,exist_ok=True)
    for preset in ('ink','smoke','liquid'):
        obj.audvis.scatter.enable=False
        engine.invalidate(); engine.audio.reset()
        scene.frame_set(1)
        bpy.ops.audvis.motion_preset(effect='scatter',preset=preset)
        obj.audvis.scatter.fluid_keep_on_loop=False
        engine.invalidate()
        for frame in range(1,73):
            scene.frame_set(frame)
            engine.on_pre_frame(scene,frame)
            if frame in (1,12,24,36,48,72):
                scene.render.filepath=str(folder/f'{preset}-{frame:03}.png')
                bpy.ops.render.render(write_still=True)
    print('PASS: rendered 18 fluid preset previews to',folder)
finally: addon.unregister()
