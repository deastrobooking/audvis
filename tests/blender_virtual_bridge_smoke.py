"""Blender bridge registration and UDP lifecycle; no external application needed."""
import importlib
import pathlib
import socket
import sys
import types
import time

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Load the bridge under an isolated package so this test needs no audio wheels.
for name, directory in [('bridge_test', ROOT), ('bridge_test.ui', ROOT/'ui'),
                        ('bridge_test.analyzer', ROOT/'analyzer')]:
    module = types.ModuleType(name)
    module.__path__ = [str(directory)]
    sys.modules[name] = module
bridge = importlib.import_module('bridge_test.ui.virtual_bridge')
osc = importlib.import_module('bridge_test.analyzer.virtual_osc')
for cls in bridge.classes:
    bpy.utils.register_class(cls)
bridge.register()
scene = bpy.context.scene
remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
remote.bind(('127.0.0.1', 0))
remote.settimeout(1)
probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
probe.bind(('127.0.0.1', 0))
port = probe.getsockname()[1]
probe.close()
calls = []
snapshots = types.ModuleType('bridge_test.ui.snapshots')
snapshots.recall = lambda owner, name: calls.append((owner.name, name)) or True
sys.modules[snapshots.__name__] = snapshots
def drain_until(count):
    deadline = time.monotonic() + 2
    while len(calls) < count and time.monotonic() < deadline:
        before = len(calls)
        bridge.tick()
        assert len(calls) - before <= 32
        time.sleep(.005)
    assert len(calls) == count, calls


try:
    scene.audvis_virtual.port = remote.getsockname()[1]
    scene.audvis_virtual.feedback_port = port
    bridge.connect(scene)
    assert len(scene.audvis_virtual.cues) == 8
    scene.audvis_virtual.cues[0].snapshot = 'Look 1'
    assert bpy.ops.audvis.virtual_bridge(action='tempo') == {'FINISHED'}
    assert osc.decode(remote.recvfrom(4096)[0]) == ('/virtual/tempo', 120)
    remote.sendto(osc.encode('/virtual/scene/1/launch', 1), ('127.0.0.1', port))
    drain_until(1)
    assert calls == [(scene.name, 'Look 1')], calls
    remote.sendto(b'invalid', ('127.0.0.1', port))
    remote.sendto(osc.encode('/virtual/scene/1/launch', 0), ('127.0.0.1', port))
    time.sleep(.02)
    bridge.tick()
    assert bridge._errors == 1 and len(calls) == 1
    # Empty assignments never recall; feedback belongs to the connected scene,
    # even when Blender's active scene changes.
    remote.sendto(osc.encode('/virtual/scene/2/launch', 1), ('127.0.0.1', port))
    time.sleep(.02)
    bridge.tick()
    assert len(calls) == 1
    other = bpy.data.scenes.new('Other bridge scene')
    bpy.context.window.scene = other
    remote.sendto(osc.encode('/virtual/scene/1/launch', 1), ('127.0.0.1', port))
    drain_until(2)
    assert calls[-1] == (scene.name, 'Look 1')
    bpy.context.window.scene = scene
    bpy.data.scenes.remove(other)
    for action, address, value in [
            ('crossfader', '/virtual/crossfader', .5),
            ('opacity', '/virtual/master/opacity', 1),
            ('blackout_on', '/virtual/master/blackout', 1),
            ('blackout_off', '/virtual/master/blackout', 0),
            ('freeze_on', '/virtual/master/freeze', 1),
            ('freeze_off', '/virtual/master/freeze', 0),
            ('cue', '/virtual/scene/8/launch', 1)]:
        assert bpy.ops.audvis.virtual_bridge(action=action, cue=8) == {'FINISHED'}
        assert osc.decode(remote.recvfrom(4096)[0]) == (address, value)
    # Main-thread work is bounded, even when a sender floods the socket.
    bridge._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    for _ in range(40):
        remote.sendto(osc.encode('/virtual/scene/1/launch', 1), ('127.0.0.1', port))
    drain_until(42)
    bridge.connect(scene)
    assert len(scene.audvis_virtual.cues) == 8
    bridge.disconnect()  # also the file-load handler
    assert bridge._socket is None and not bridge._values
    bridge.connect(scene)
    scene.name = 'Renamed bridge owner'
    bridge.tick()
    assert bridge._socket is None
    print('PASS: bridge registration, UDP command, snapshot dispatch, bounds and cleanup')
finally:
    remote.close()
    bridge.unregister()
    for cls in reversed(bridge.classes):
        bpy.utils.unregister_class(cls)
