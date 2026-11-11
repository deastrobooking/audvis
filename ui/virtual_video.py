"""Session-only AudVis image/viewport sender for VIRTUAL's provisional RGBA stream."""
import socket
import threading
import time

import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent

from ..analyzer.virtual_video import MAX_HEIGHT, MAX_WIDTH, pack_header
from .buttonspanel import AudVisButtonsPanel_Npanel

_handler = None
_area_pointer = None
_worker = None
_measure_only = False
_source_mode = None
_owner_scene = None
_state_lock = threading.Lock()
_state = {
    'status': 'Stopped', 'width': 0, 'height': 0, 'sent': 0, 'captured': 0,
    'dropped': 0, 'readback_ms': 0.0, 'fps': 0.0,
}
_last_status_redraw = 0.0
_last_send_count = 0
_last_fps_time = 0.0
_sequence = 0
_last_image_capture = 0.0


class _Sender:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.pending = None
        self.sock = None
        self.thread = threading.Thread(target=self.run, name='AudVis-VIRTUAL-video', daemon=True)

    def start(self):
        self.thread.start()

    def offer(self, packet, payload, width, height, readback_ms):
        with self.condition:
            if self.stop_event.is_set():
                return
            if self.pending is not None:
                with _state_lock:
                    _state['dropped'] += 1
            self.pending = (packet, payload, width, height)
            self.condition.notify()
        with _state_lock:
            _state['width'], _state['height'] = width, height
            _state['readback_ms'] = readback_ms

    def close(self):
        self.stop_event.set()
        with self.condition:
            self.pending = None
            self.condition.notify_all()
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)

    def run(self):
        global _worker
        failure = None
        while not self.stop_event.is_set():
            sock = None
            try:
                with _state_lock:
                    _state['status'] = f'Connecting to {self.host}:{self.port}'
                sock = socket.create_connection((self.host, self.port), timeout=.5)
                sock.settimeout(.5)
                self.sock = sock
                with _state_lock:
                    _state['status'] = 'Connected; waiting for viewport frame'
                while not self.stop_event.is_set():
                    with self.condition:
                        while self.pending is None and not self.stop_event.is_set():
                            self.condition.wait(.25)
                        item, self.pending = self.pending, None
                    if item is None:
                        continue
                    packet, payload, _width, _height = item
                    sock.sendall(packet)
                    sock.sendall(payload)
                    with _state_lock:
                        _state['sent'] += 1
                        _state['status'] = f'Sending to {self.host}:{self.port}'
            except OSError as error:
                if not self.stop_event.is_set():
                    failure = f'Stream stopped after socket error: {error}'
                    break
            finally:
                self.sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
        with _state_lock:
            _state['status'] = failure or 'Stopped'
        if _worker is self:
            _worker = None


def _viewport_draw():
    global _sequence
    sender = _worker
    if (sender is None and not _measure_only) or (sender is not None and sender.stop_event.is_set()):
        return
    context = bpy.context
    area = context.area
    region = context.region
    if area is None or area.type != 'VIEW_3D' or area.as_pointer() != _area_pointer:
        return
    if region is None or region.type != 'WINDOW':
        return
    width, height = int(region.width), int(region.height)
    if width <= 0 or height <= 0:
        return
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        with _state_lock:
            _state['status'] = f'Viewport exceeds {MAX_WIDTH} × {MAX_HEIGHT} limit'
        return
    now = time.monotonic()
    wm = context.window_manager
    fps = max(1, min(60, wm.audvis_virtual_video_fps))
    last_capture = getattr(_viewport_draw, 'last_capture', 0.0)
    if now - last_capture < 1.0 / fps:
        return
    _viewport_draw.last_capture = now
    capture_ns = time.monotonic_ns()
    started = time.perf_counter()
    try:
        framebuffer = gpu.state.active_framebuffer_get()
        pixels = framebuffer.read_color(0, 0, width, height, 4, 0, 'UBYTE')
        try:
            raw = bytes(memoryview(pixels))
        except TypeError:
            raw = bytes(pixels.to_list())
        row_bytes = width * 4
        if len(raw) != row_bytes * height:
            raise ValueError('Framebuffer returned an unexpected pixel count')
        # OpenGL framebuffer reads start at the bottom-left; the wire rows are top-to-bottom.
        payload = b''.join(raw[offset:offset + row_bytes]
                           for offset in range(len(raw) - row_bytes, -1, -row_bytes))
        readback_ms = (time.perf_counter() - started) * 1000.0
        with _state_lock:
            _state['width'], _state['height'] = width, height
            _state['readback_ms'] = readback_ms
            _state['captured'] += 1
        if sender is not None:
            _sequence = (_sequence + 1) & 0xFFFFFFFFFFFFFFFF
            packet = pack_header(width, height, _sequence, capture_ns)
            sender.offer(packet, payload, width, height, readback_ms)
    except (RuntimeError, ValueError, BufferError) as error:
        with _state_lock:
            _state['status'] = f'Viewport readback failed: {error}'


def output_image_updated(scene, image):
    """Copy AudVis's selected Output Image after its normal refresh hook."""
    global _sequence, _last_image_capture
    if _source_mode != 'image' or scene.name != _owner_scene:
        return
    if _worker is None and not _measure_only:
        return
    if image is None or scene.audvis.video_image is None:
        return
    try:
        if image.as_pointer() != scene.audvis.video_image.as_pointer():
            return
        now = time.monotonic()
        wm = bpy.context.window_manager
        fps = max(1, min(60, wm.audvis_virtual_video_fps)) if wm is not None else 30
        if now - _last_image_capture < 1.0 / fps:
            return
        _last_image_capture = now
        capture_ns = time.monotonic_ns()
        started = time.perf_counter()
        if image.source == 'FILE' and image.filepath:
            image.reload()
        width, height = (int(value) for value in image.size)
        if width <= 0 or height <= 0 or width > MAX_WIDTH or height > MAX_HEIGHT:
            raise ValueError(f'Output Image dimensions exceed {MAX_WIDTH} × {MAX_HEIGHT}')
        rgba = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(rgba)
        rgba = np.nan_to_num(rgba, nan=0.0, posinf=1.0, neginf=0.0)
        rgba = np.clip(rgba.reshape(height, width, 4), 0.0, 1.0)
        # Blender exposes scene-linear pixels; encode RGB for the RGBA8 stream.
        rgb = rgba[:, :, :3]
        rgba[:, :, :3] = np.where(
            rgb <= 0.0031308, rgb * 12.92,
            1.055 * np.power(rgb, 1.0 / 2.4) - 0.055)
        payload = np.rint(rgba[::-1, :, :] * 255.0).astype(np.uint8).tobytes()
        readback_ms = (time.perf_counter() - started) * 1000.0
        with _state_lock:
            _state['width'], _state['height'] = width, height
            _state['readback_ms'] = readback_ms
            _state['captured'] += 1
        sender = _worker
        if sender is not None:
            _sequence = (_sequence + 1) & 0xFFFFFFFFFFFFFFFF
            sender.offer(pack_header(width, height, _sequence, capture_ns),
                         payload, width, height, readback_ms)
    except (RuntimeError, ValueError, BufferError, ReferenceError) as error:
        with _state_lock:
            _state['status'] = f'Output Image read failed: {error}'


def _remove_draw_handler():
    global _handler, _area_pointer
    if _handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        except (RuntimeError, ValueError):
            pass
    _handler = None
    _area_pointer = None


def stop(_dummy=None):
    global _worker, _measure_only, _source_mode, _owner_scene
    _remove_draw_handler()
    worker, _worker = _worker, None
    if worker is not None:
        worker.close()
    _measure_only = False
    _source_mode = None
    _owner_scene = None
    with _state_lock:
        _state.update(status='Stopped', width=0, height=0, fps=0.0)


class AUDVIS_OT_virtualVideo(bpy.types.Operator):
    bl_idname = 'audvis.virtual_video'
    bl_label = 'VIRTUAL Video Stream'
    bl_description = 'Stream the selected AudVis Output Image or current viewport to VIRTUAL'
    action: bpy.props.EnumProperty(items=[('viewport', 'Viewport', ''), ('image', 'Output Image', ''),
                                           ('measure_image', 'Measure Image', ''), ('stop', 'Stop', '')])

    def execute(self, context):
        global _handler, _area_pointer, _worker, _sequence, _measure_only
        global _source_mode, _owner_scene, _last_image_capture
        global _last_send_count, _last_fps_time
        if self.action == 'stop':
            stop()
            return {'FINISHED'}
        image_mode = self.action in {'image', 'measure_image'}
        if not image_mode and (context.area is None or context.area.type != 'VIEW_3D'):
            self.report({'ERROR'}, 'Start the stream from a 3D Viewport')
            return {'CANCELLED'}
        if image_mode and context.scene.audvis.video_image is None:
            self.report({'ERROR'}, 'Choose an Output Image in AudVis Video Capture first')
            return {'CANCELLED'}
        stop()
        wm = context.window_manager
        host = wm.audvis_virtual_video_host.strip()
        port = wm.audvis_virtual_video_port
        if host not in {'127.0.0.1', 'localhost'}:
            self.report({'ERROR'}, 'The VIRTUAL video stream is restricted to localhost')
            return {'CANCELLED'}
        _sequence = 0
        _last_image_capture = 0.0
        _last_send_count, _last_fps_time = 0, 0.0
        _source_mode = 'image' if image_mode else 'viewport'
        _owner_scene = context.scene.name if image_mode else None
        _area_pointer = None if image_mode else context.area.as_pointer()
        measure_only = self.action == 'measure_image'
        _measure_only = measure_only
        _worker = None if measure_only else _Sender('127.0.0.1', port)
        try:
            if not image_mode:
                _handler = bpy.types.SpaceView3D.draw_handler_add(
                    _viewport_draw, (), 'WINDOW', 'POST_PIXEL')
            if _worker is not None:
                _worker.start()
        except Exception as error:
            stop()
            self.report({'ERROR'}, f'Could not start viewport sender: {error}')
            return {'CANCELLED'}
        with _state_lock:
            _state.update(status=('Measuring Output Image copy without networking' if measure_only
                                  else f'Connecting to 127.0.0.1:{port}'), sent=0,
                          captured=0, dropped=0, readback_ms=0.0, fps=0.0)
        if image_mode:
            output_image_updated(context.scene, context.scene.audvis.video_image)
        return {'FINISHED'}


class AUDVIS_PT_virtualVideo(AudVisButtonsPanel_Npanel):
    bl_idname = 'AUDVIS_PT_virtualVideo'
    bl_label = 'VIRTUAL Video Stream'
    bl_parent_id = 'AUDVIS_PT_virtualBridge'

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        with _state_lock:
            state = dict(_state)
        row = layout.row(align=True)
        row.prop(context.window_manager, 'audvis_virtual_video_host', text='Host')
        row.prop(context.window_manager, 'audvis_virtual_video_port', text='Port')
        layout.prop(context.window_manager, 'audvis_virtual_video_fps', text='Target FPS')
        row = layout.row(align=True)
        op = row.operator('audvis.virtual_video', text='Send Output Image', icon='PLAY')
        op.action = 'image'
        op = row.operator('audvis.virtual_video', text='Measure Image')
        op.action = 'measure_image'
        op = row.operator('audvis.virtual_video', text='Viewport source')
        op.action = 'viewport'
        op = row.operator('audvis.virtual_video', text='Stop', icon='PAUSE')
        op.action = 'stop'
        layout.label(text=state['status'])
        layout.label(text=f"Frame: {state['width']} × {state['height']} · {state['fps']:.1f} fps")
        count_label = 'Captured' if _measure_only else 'Sent'
        count = state['captured'] if _measure_only else state['sent']
        layout.label(text=f"{count_label}: {count} · dropped pending: {state['dropped']}")
        if state['readback_ms']:
            label = 'Image reload + copy' if _source_mode == 'image' else 'Readback + copy'
            layout.label(text=f"{label}: {state['readback_ms']:.1f} ms")
        layout.label(text='Output Image follows the existing AudVis Video Capture selector.')


def _timer():
    global _last_send_count, _last_fps_time, _last_status_redraw
    now = time.monotonic()
    with _state_lock:
        elapsed = now - _last_fps_time if _last_fps_time else 0.0
        if elapsed >= 1.0:
            count = _state['captured'] if _measure_only else _state['sent']
            _state['fps'] = (count - _last_send_count) / elapsed
            _last_send_count, _last_fps_time = count, now
    if _worker is None and _handler is not None:
        _remove_draw_handler()
    if now - _last_status_redraw >= .5:
        _last_status_redraw = now
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    return .25


@persistent
def _render_output_image(scene):
    if _source_mode == 'image' and scene.name == _owner_scene:
        output_image_updated(scene, scene.audvis.video_image)


def register():
    bpy.types.WindowManager.audvis_virtual_video_host = bpy.props.StringProperty(
        name='Host', default='127.0.0.1', options={'SKIP_SAVE'})
    bpy.types.WindowManager.audvis_virtual_video_port = bpy.props.IntProperty(
        name='Port', default=9010, min=1024, max=65535, options={'SKIP_SAVE'})
    bpy.types.WindowManager.audvis_virtual_video_fps = bpy.props.IntProperty(
        name='Target FPS', default=30, min=1, max=60, options={'SKIP_SAVE'})
    if stop not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(stop)
    if _render_output_image not in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.append(_render_output_image)
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, persistent=True)


def unregister():
    stop()
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    if stop in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(stop)
    if _render_output_image in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.remove(_render_output_image)
    del bpy.types.WindowManager.audvis_virtual_video_host
    del bpy.types.WindowManager.audvis_virtual_video_port
    del bpy.types.WindowManager.audvis_virtual_video_fps


classes = [AUDVIS_OT_virtualVideo, AUDVIS_PT_virtualVideo]
