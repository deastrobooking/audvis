"""Loopback VIRTUAL controls and feedback. Socket work is bounded on Blender's timer."""
import socket
import time

import bpy
from bpy.app.handlers import persistent
from ..analyzer.virtual_osc import MAX_PACKET, encode, decode, scene_cue
from .buttonspanel import AudVisButtonsPanel_Npanel

_socket = None
_owner = None
_target = None
_status = 'Disconnected'
_last_feedback = None
_values = {}
_errors = 0


class AUDVIS_PG_virtualCue(bpy.types.PropertyGroup):
    snapshot: bpy.props.StringProperty(name='Snapshot', description='Snapshot recalled when this VIRTUAL scene launches')


class AUDVIS_PG_virtualBridge(bpy.types.PropertyGroup):
    port: bpy.props.IntProperty(name='VIRTUAL Port', default=9000, min=1024, max=65535, description='VIRTUAL OSC input port on this computer')
    feedback_port: bpy.props.IntProperty(name='Feedback Port', default=9001, min=1024, max=65535, description='Local port receiving VIRTUAL OSC feedback')
    tempo: bpy.props.FloatProperty(name='BPM', default=120, min=20, max=400, description='Tempo sent to VIRTUAL; this does not synchronize Blender beat phase')
    crossfader: bpy.props.FloatProperty(name='Crossfader', default=.5, min=0, max=1, description='A/B mix sent to VIRTUAL')
    opacity: bpy.props.FloatProperty(name='Master', default=1, min=0, max=1, description='Master opacity sent to VIRTUAL')
    cues: bpy.props.CollectionProperty(type=AUDVIS_PG_virtualCue)


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


@persistent
def disconnect(_dummy=None):
    global _socket, _owner, _target, _status, _last_feedback, _errors
    if _socket is not None:
        _socket.close()
    _socket = _owner = _target = _last_feedback = None
    _status = 'Disconnected'
    _values.clear()
    _errors = 0


def connect(scene):
    global _socket, _owner, _target, _status
    disconnect()
    props = scene.audvis_virtual
    if props.port == props.feedback_port:
        raise ValueError('Input and feedback ports must differ')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        sock.bind(('127.0.0.1', props.feedback_port))
    except OSError:
        sock.close()
        raise
    while len(props.cues) < 8:
        props.cues.add()
    _socket, _owner = sock, scene.name
    _target = ('127.0.0.1', props.port)
    _status = 'Listening; waiting for VIRTUAL feedback'


def tick():
    global _status, _last_feedback, _errors
    if _socket is None:
        return .03
    scene = bpy.data.scenes.get(_owner)
    if scene is None:
        disconnect()
        return .03
    changed = False
    for _ in range(32):
        try:
            packet, sender = _socket.recvfrom(MAX_PACKET + 1)
        except BlockingIOError:
            break
        except OSError as error:
            disconnect()
            _status = str(error)
            break
        if sender[0] != '127.0.0.1':
            continue
        try:
            address, value = decode(packet)
        except (ValueError, UnicodeError):
            _errors += 1
            changed = True
            continue
        # Retain only the values displayed by this panel, bounding runtime memory.
        if address in {'/virtual/tempo', '/virtual/crossfader', '/virtual/master/opacity',
                       '/virtual/master/blackout', '/virtual/master/freeze'}:
            _values[address] = value
        _last_feedback = time.monotonic()
        _status = 'Receiving VIRTUAL feedback'
        cue = scene_cue(address, value)
        if cue is not None and cue < len(scene.audvis_virtual.cues):
            name = scene.audvis_virtual.cues[cue].snapshot
            if name:
                from .snapshots import recall
                if not recall(scene, name):
                    _status = 'Missing snapshot: ' + name
        changed = True
    if changed:
        _redraw()
    return .03


class AUDVIS_OT_virtualBridge(bpy.types.Operator):
    bl_idname = 'audvis.virtual_bridge'
    bl_label = 'VIRTUAL Bridge'
    bl_description = 'Connect locally or send a VIRTUAL performance command'
    action: bpy.props.StringProperty(default='connect')
    cue: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        global _status
        try:
            if self.action == 'disconnect':
                disconnect()
            elif self.action == 'connect':
                connect(context.scene)
            else:
                if _socket is None or context.scene.name != _owner:
                    self.report({'WARNING'}, 'Connect the bridge from this scene first')
                    return {'CANCELLED'}
                p = context.scene.audvis_virtual
                routes = {
                    'tempo': ('/virtual/tempo', p.tempo),
                    'crossfader': ('/virtual/crossfader', p.crossfader),
                    'opacity': ('/virtual/master/opacity', p.opacity),
                    'blackout_on': ('/virtual/master/blackout', 1),
                    'blackout_off': ('/virtual/master/blackout', 0),
                    'freeze_on': ('/virtual/master/freeze', 1),
                    'freeze_off': ('/virtual/master/freeze', 0),
                    'cue': (f'/virtual/scene/{self.cue}/launch', 1),
                }
                address, value = routes[self.action]
                _socket.sendto(encode(address, value), _target)
                _status = 'Command sent; check feedback for acceptance'
        except (OSError, ValueError, KeyError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        _redraw()
        return {'FINISHED'}


class AUDVIS_PT_virtualBridge(AudVisButtonsPanel_Npanel):
    bl_label = 'VIRTUAL Bridge'

    def draw(self, context):
        layout = self.layout
        p = context.scene.audvis_virtual
        layout.label(text=_status)
        if _last_feedback is not None:
            layout.label(text=f'Last feedback: {time.monotonic() - _last_feedback:.1f}s ago')
        if _errors:
            layout.label(text=f'Ignored malformed packets: {_errors}')
        if _owner is not None:
            layout.label(text='Connected scene: ' + _owner)
        settings = layout.column()
        settings.enabled = _socket is None
        settings.prop(p, 'port')
        settings.prop(p, 'feedback_port')
        row = layout.row()
        row.operator('audvis.virtual_bridge', text='Connect / Reconnect').action = 'connect'
        row.operator('audvis.virtual_bridge', text='Disconnect').action = 'disconnect'
        layout.label(text='VIRTUAL: Listen on 127.0.0.1:' + str(p.port))
        layout.label(text='Feedback target: 127.0.0.1:' + str(p.feedback_port))
        controls = layout.column()
        controls.enabled = _socket is not None and _owner == context.scene.name
        for prop, action in [('tempo', 'tempo'), ('crossfader', 'crossfader'), ('opacity', 'opacity')]:
            row = controls.row(align=True)
            row.prop(p, prop)
            row.operator('audvis.virtual_bridge', text='Send').action = action
        for title, route in [('Blackout', 'blackout'), ('Freeze', 'freeze')]:
            row = controls.row(align=True)
            row.label(text=title)
            for label, suffix in [('On', '_on'), ('Off', '_off')]:
                row.operator('audvis.virtual_bridge', text=label).action = route + suffix
            value = _values.get('/virtual/master/' + route)
            row.label(text='?' if value is None else ('ON' if value >= .5 else 'OFF'))
        tempo = _values.get('/virtual/tempo')
        if tempo is not None:
            controls.label(text=f'VIRTUAL tempo: {tempo:.1f} BPM (tempo only)')
        controls.label(text='Scene launch → Blender snapshot')
        for i, cue in enumerate(p.cues):
            row = controls.row(align=True)
            op = row.operator('audvis.virtual_bridge', text=str(i + 1))
            op.action, op.cue = 'cue', i + 1
            row.prop_search(cue, 'snapshot', context.scene.audvis, 'snapshots', text='')
        layout.label(text='Snapshot recall requires VIRTUAL feedback.')


def register():
    bpy.types.Scene.audvis_virtual = bpy.props.PointerProperty(type=AUDVIS_PG_virtualBridge)
    if disconnect not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(disconnect)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, persistent=True)


def unregister():
    disconnect()
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    if disconnect in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(disconnect)
    del bpy.types.Scene.audvis_virtual


classes = [AUDVIS_PG_virtualCue, AUDVIS_PG_virtualBridge, AUDVIS_OT_virtualBridge, AUDVIS_PT_virtualBridge]
