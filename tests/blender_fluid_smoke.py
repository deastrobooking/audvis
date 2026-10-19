"""Fluid numerical stability, cache roundtrip and prepared mesh replay."""
import importlib
import pathlib
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import bpy
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
p = bpy.context.preferences.addons.new(); p.module = ROOT.name
addon.register()
fluid = importlib.import_module(ROOT.name + '.analyzer.motion.fluid')
scatter = importlib.import_module(ROOT.name + '.analyzer.motion.scatter')
presets = importlib.import_module(ROOT.name + '.ui.motion_presets')
try:
    scene = bpy.context.scene
    scene.audvis.motion_enable = True
    obj = bpy.context.object
    s = obj.audvis.scatter
    s.style = 'fluid'
    s.fluid_keep_on_loop = False
    centers = np.array([[1.,0,0], [0,1.,0], [0,0,1.]])
    f = fluid.Flow(centers, 24, 3, 1)
    rng = np.random.default_rng(5)
    v = fluid.project(rng.normal(size=f.velocity.shape), f.kv, f.k2)
    assert np.abs(fluid.periodic_divergence(v, f.h)).max() < 1e-10
    timings = []
    for i in range(300):
        start = time.perf_counter()
        f.step(s, .5, i/24, 1/24, centers, None)
        timings.append(time.perf_counter()-start)
    assert np.isfinite(f.pos).all()
    assert np.linalg.norm(f.velocity, axis=-1).max() <= fluid.MAX_SPEED*f.half + 1e-8
    print('Fluid resolution 24 median ms:', np.median(timings)*1000)
    s.fluid_burst = s.fluid_swirl = s.fluid_turbulence = s.fluid_vorticity = s.fluid_buoyancy = 0
    s.fluid_return = 1
    f.velocity[:] = 0; f.vel[:] = 0
    f.pos += .5
    before = np.linalg.norm(f.pos-centers)
    for i in range(240): f.step(s, 0, i/24, 1/24, centers, None)
    assert np.linalg.norm(f.pos-centers) < before*.01
    f.reset(centers, 1)
    def step(dt): f.pos += dt
    for frame in range(2, 10): assert f.advance(frame,1,10,24,step,False)
    position = f.history[5][0].copy()
    assert f.advance(5,1,10,24,step,False)
    assert np.array_equal(position,f.pos)
    assert not f.advance(1,1,10,24,step,False)
    f.reset(centers,10)
    assert f.advance(1,1,10,24,step,True)
    assert not np.array_equal(f.pos,centers)
    # Apply each preset through the real operator.
    for name in ('ink','smoke','liquid'):
        bpy.ops.audvis.motion_preset(effect='scatter', preset=name)
        assert s.style == 'fluid'
    bpy.ops.audvis.motion_preset(effect='scatter', preset='supernova')
    assert s.style == 'explode'
    bpy.ops.audvis.motion_preset(effect='scatter', preset='liquid')
    # Exact geometry playback from a disk archive, arbitrary frame order.
    s.fluid_keep_on_loop = False
    scene.frame_start, scene.frame_end = 1, 12
    engine = bpy.audvis._get_motion_engine()
    engine.driver = lambda *args, **kwargs: 1.0
    engine.invalidate()
    engine.audio.reset()
    stream = {'fingerprint': None, 'frames': {}}
    coordinates = {}
    for frame in range(1,13):
        scene.frame_set(frame)
        engine.on_pre_frame(scene,frame)
        cache = engine._cache[('scatter',obj.name)][1]
        flow = cache['flow']
        stream['fingerprint'] = fluid.fingerprint(cache['rest'],cache['pieces'])
        stream['frames'][frame] = flow.pos.copy(), flow.rot.copy()
        co = np.empty(len(obj.data.vertices)*3)
        obj.data.vertices.foreach_get('co',co)
        coordinates[frame] = co
    with tempfile.TemporaryDirectory() as folder:
        path = str(pathlib.Path(folder)/'bake.npz')
        fluid.save_bake(path, {'mesh': stream})
        loaded = fluid.load_bake(path)['mesh'][1]
        assert len(loaded) == 12
        for frame in loaded:
            for a,b in zip(loaded[frame],stream['frames'][frame]): assert np.array_equal(a,b)
        s.fluid_bake_path, s.fluid_use_bake = path, True
        for frame in (12,1,6,2,10):
            scene.frame_set(frame)
            engine.on_pre_frame(scene,frame)
            co = np.empty(len(obj.data.vertices)*3)
            obj.data.vertices.foreach_get('co',co)
            assert np.array_equal(co,coordinates[frame]), frame
        bpy.ops.audvis.motion_fluid_clear()
        assert not s.fluid_use_bake and pathlib.Path(path).exists()
    # Exercise modal bake completion and cancellation with a headless timer harness.
    bake_ui = importlib.import_module(ROOT.name + '.ui.fluid_bake')
    with tempfile.TemporaryDirectory() as folder:
        bpy.ops.wm.save_as_mainfile(filepath=str(pathlib.Path(folder)/'show.blend'))
        timer = object()
        context = NS(object=obj, scene=scene, screen=NS(is_animation_playing=False),
                     window=bpy.context.window,
                     workspace=NS(status_text_set=lambda text: None),
                     window_manager=NS(event_timer_add=lambda *a, **k: timer,
                                       modal_handler_add=lambda op: None,
                                       event_timer_remove=lambda timer: None))
        errors = []
        op = NS(report=lambda kind, text: errors.append(text))
        op.finish = lambda ctx, success: bake_ui.AUDVIS_OT_motionFluidBake.finish(op,ctx,success)
        s.fluid_use_bake = False
        assert bake_ui.AUDVIS_OT_motionFluidBake.invoke(op, context, NS()) == {'RUNNING_MODAL'}
        for frame in range(scene.frame_start,scene.frame_end+1):
            result = bake_ui.AUDVIS_OT_motionFluidBake.modal(op,context,NS(type='TIMER'))
        assert result == {'FINISHED'} and not errors, errors
        assert s.fluid_use_bake
        archive = pathlib.Path(bpy.path.abspath(s.fluid_bake_path))
        assert archive.exists()
        assert len(fluid.load_bake(str(archive))['mesh'][1]) == 12
        saved = archive.read_bytes()
        assert bake_ui.AUDVIS_OT_motionFluidBake.invoke(op,context,NS()) == {'RUNNING_MODAL'}
        assert bake_ui.AUDVIS_OT_motionFluidBake.modal(op,context,NS(type='ESC')) == {'CANCELLED'}
        assert s.fluid_use_bake and archive.read_bytes() == saved
        s.fluid_use_bake = False
    print('PASS: Fluid stability, presets, archive, geometry replay and modal lifecycle')
finally:
    addon.unregister()
