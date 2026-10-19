"""Integration probes called by blender_midi_map_smoke after its existing checks."""
import importlib
import json
import pathlib
import tempfile
import time
from queue import Queue
from types import SimpleNamespace as NS
from unittest.mock import patch

import bpy


def run(root, scene):
    mapping = importlib.import_module(root + '.ui.midi.mapping')
    profiles = importlib.import_module(root + '.ui.midi.profiles')
    snapshots = importlib.import_module(root + '.ui.snapshots')
    beat = importlib.import_module(root + '.ui.beat')
    eq = importlib.import_module(root + '.ui.eq')
    motion = importlib.import_module(root + '.ui.motion')
    thread_mod = importlib.import_module(root + '.analyzer.midi_realtime.midi_thread')
    audio = importlib.import_module(root + '.analyzer.motion.audio')
    # Proxy lines: clock bypasses Learn; snapshot dictionaries stay immutable.
    t = thread_mod.MidiThread()
    t.data, t.data_controls, t.note_counts = {}, {}, {}
    t.last_notes_list = thread_mod.LastNotesList()
    q = Queue()
    t.inputs = {'Device': {'queue': q}}
    for line in ('start 0', *[f'clock {i/48}' for i in range(97)], 'stop 2'):
        q.put(line)
    t._receive()
    assert t.last_msg is None and not t.recent
    assert abs(t.clocks['Device'].bpm(2)-120) < 1e-6
    assert not t.clocks['Device'].running
    q.put('1 c7 80'); q.put('1 60 100')
    t._receive()
    before = (t.data, t.data_controls, t.note_counts)
    q.put('1 c7 90'); q.put('1 60 0'); q.put('1 60 0')
    t._receive()
    assert before[0]['Device'][1][60] == 100
    assert before[1]['Device'][1][7] == 80
    assert before[2]['Device'][1][60] == 1
    for i in range(12): q.put(f'1 c{i} 10')
    t._receive()
    assert len(t.recent) == 8

    maps = scene.audvis.midi_realtime.maps
    maps.clear()
    # Frame handler uses new sound links even with MIDI realtime disabled.
    scene.audvis.midi_realtime.enable = False
    path = mapping.full_path_of(scene, 'audvis.motion_master')
    m = mapping.create(scene, 'eq', 3, full_path=path)
    m.range_min, m.range_max = 0, 1
    orig_driver = bpy.audvis.driver
    bpy.audvis.driver = lambda *a, **kw: 5.0
    mapping._sound_frames.clear()
    scene.frame_set(21)
    assert abs(scene.audvis.motion_master-.5) < 1e-6, scene.audvis.motion_master
    maps.clear()
    m = mapping.create(scene, 'beat', 1, full_path=path)
    scene.audvis.beat_source = 'audio'
    beat._trackers.clear()
    scene.frame_set(1)
    scene.frame_set(7)
    assert abs(scene.audvis.motion_master-.5) < 1e-5, scene.audvis.motion_master
    # Beat envelopes detect counter changes and remain stable on repeated frames.
    a = audio.MotionAudio()
    props = scene.objects.get('Cube').audvis.scatter.audio if scene.objects.get('Cube') else None
    if props is None:
        bpy.ops.mesh.primitive_cube_add(); props = bpy.context.object.audvis.scatter.audio
    props.response = 'beat'; props.beat_every = '1'; props.trigger_length = 10
    tracker = beat.tracker(scene)
    tracker.counter = 0
    assert a.values('beat-test', props, lambda *a, **kw: 0, 2, scene, 1) == [0,0]
    tracker.counter = 1
    assert a.values('beat-test', props, lambda *a, **kw: 0, 2, scene, 2) == [1,1]
    assert a.values('beat-test', props, lambda *a, **kw: 0, 2, scene, 2) == [1,1]
    # Capture and morph numeric properties, with no real clock wait.
    maps.clear()
    scene.audvis.snapshots.clear()
    scene.audvis.motion_master = .2
    s = scene.audvis.snapshots.add(); s.name = 'Quiet'
    snapshots.capture(scene,s)
    assert any(v.full_path == path for v in s.values)
    scene.audvis.motion_master = 1
    scene.audvis.motion_fade_time = 2
    with patch.object(snapshots.time, 'monotonic', return_value=100):
        assert snapshots.recall(scene,'Quiet')
    with patch.object(snapshots.time, 'monotonic', return_value=101): snapshots.tick()
    assert abs(scene.audvis.motion_master-.6) < 1e-5
    with patch.object(snapshots.time, 'monotonic', return_value=102): snapshots.tick()
    assert abs(scene.audvis.motion_master-.2) < 1e-5
    scene.audvis.motion_fade_time = 0
    m = mapping.create(scene,'note',60,action='snapshot'); m.snapshot_name = 'Quiet'
    scene.audvis.motion_master = 1
    mapping.run_action(m)
    assert abs(scene.audvis.motion_master-.2) < 1e-5
    m.action = 'tap'
    with patch.object(beat.time,'monotonic',return_value=200): mapping.run_action(m)
    with patch.object(beat.time,'monotonic',return_value=200.5): mapping.run_action(m)
    assert beat.tracker(scene).bpm == 120
    # Profiles retain all settings, regenerate uid, append or replace; bank fills paths.
    maps.clear()
    m = mapping.create(scene,'cc',10,full_path=mapping.full_path_of(scene,'audvis.eq_band_1.gain'))
    m.range_min, m.range_max, m.smoothing = -.5, 2.5, .4
    original_uid = m.uid
    assert profiles.fill_bank(scene,0,8) == 7
    assert maps[7].number == 17 and maps[7].data_path == 'audvis.eq_band_8.gain'
    with tempfile.TemporaryDirectory() as folder:
        file = str(pathlib.Path(folder)/'profile.json')
        profiles.export_profile(scene,file)
        expected = [profiles.fields(m) for m in maps]
        profiles.import_profile(scene,file,True)
        assert expected == [profiles.fields(m) for m in maps]
        assert maps[0].uid != original_uid
        profiles.import_profile(scene,file,False)
        assert len(maps) == 16
        with open(file,'w') as f: json.dump({'version': 1, 'mappings':[{'kind':'invalid'}]},f)
        try: profiles.import_profile(scene,file,True)
        except ValueError: pass
        else: raise AssertionError('invalid profile accepted')
        assert len(maps) == 16

    # Validate operators, properties, icons and enum values in new UI branches.
    icons = {i.identifier for i in bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items}
    class Op:
        def __init__(self,rna): object.__setattr__(self,'rna',rna)
        def __setattr__(self,key,value):
            p = self.rna.properties.get(key)
            assert p is not None, key
            if p.type == 'ENUM': assert value in {i.identifier for i in p.enum_items}, (key,value)
    class Layout:
        def __getattr__(self,name):
            def call(*args,**kwargs):
                if 'icon' in kwargs: assert kwargs['icon'] in icons, kwargs['icon']
                if name == 'prop':
                    assert args[1] in args[0].bl_rna.properties, args[1]
                if name == 'operator':
                    category,op = args[0].split('.')
                    return Op(getattr(getattr(bpy.ops,category),op).get_rna_type())
                return Layout()
            return call
    context = bpy.context
    mode = importlib.import_module(root + '.ui.midi.map_mode')
    mode_context = NS(scene=scene, active_object=context.active_object, window=context.window, workspace=None,
                      window_manager=NS(windows=[], event_timer_add=lambda *a, **k: None,
                                        event_timer_remove=lambda t: None, modal_handler_add=lambda op: None))
    mode_op = NS(_analyzer=mode.AUDVIS_OT_midiMapMode._analyzer, report=lambda *a: None)
    mode_op._finish = lambda ctx: mode.AUDVIS_OT_midiMapMode._finish(mode_op,ctx)
    assert mode.AUDVIS_OT_midiMapMode.invoke(mode_op,mode_context,NS()) == {'RUNNING_MODAL'}
    mode.arm(path)
    mode.draw_button(Layout(),mode_context)
    assert mode.AUDVIS_OT_midiMapMode.modal(mode_op,mode_context,NS(type='TIMER',value='NOTHING')) == {'PASS_THROUGH'}
    assert mode.AUDVIS_OT_midiMapLink.execute(NS(kind='eq',number=2),mode_context) == {'FINISHED'}
    assert maps[-1].kind == 'eq' and maps[-1].number == 2
    mode_op._finish(mode_context)
    for cls in (beat.AUDVIS_PT_beatNpanel,snapshots.AUDVIS_PT_snapshotsNpanel,mapping.AUDVIS_PT_midiMapsNpanel):
        cls.draw(NS(layout=Layout()),context)
    for item in scene.audvis.snapshots:
        snapshots.AUDVIS_UL_snapshots.draw_item(NS(),context,Layout(),None,item,0,None,'',0)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.audvis.motion_preset(effect='scatter',preset='ink')
    proxy = NS(layout=Layout(), _draw_fluid=motion.AUDVIS_PT_motionScatterNpanel._draw_fluid)
    motion.AUDVIS_PT_motionScatterNpanel.draw(proxy, context)
    for source in ('audio', 'midi', 'tap'):
        scene.audvis.beat_source = source
        beat.AUDVIS_PT_beatNpanel.draw(NS(layout=Layout()),context)
    scene.audvis.beat_source = 'audio'
    # End-only switching remains gated; bars consume each boundary once.
    switch = importlib.import_module(root + '.switchscenes')
    dummy = NS(audvis=NS(realtime_enable=True, realtime_switchscenes=True, realtime_switch_bars=1),
               frame_current=2, frame_start=1, frame_end=250, as_pointer=lambda: -1)
    other = NS(audvis=NS(realtime_switch_bars=0), frame_start=1)
    fake_bpy = NS(data=NS(scenes=[dummy,other],particles=[]),
                  context=NS(window=NS(scene=dummy),screen=NS(is_animation_playing=True)))
    fake_tracker = NS(counter=0)
    beat._switches.pop(-1,None)
    with patch.object(switch,'bpy',fake_bpy), patch.object(beat,'tracker',return_value=fake_tracker), patch.object(switch,'switch_window_scene') as switched:
        assert not switch.try_switch_scenes(dummy)
        fake_tracker.counter=4
        assert switch.try_switch_scenes(dummy)
        dummy.frame_current=2
        assert not switch.try_switch_scenes(dummy)
        assert switched.call_count == 1
    start = time.perf_counter()
    maps.clear()
    for i in range(8): mapping.create(scene,'eq',i+1,full_path=path)
    for i in range(100):
        beat.update(scene)
        mapping.apply_sound(scene)
    print('Beat + 8 Sound Links mean ms:',(time.perf_counter()-start)*10)
    bpy.audvis.driver = orig_driver
    snapshots._jobs.clear()
    print('PASS: live feature integration and strict panel probe')
