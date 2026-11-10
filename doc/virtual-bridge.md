# VIRTUAL Bridge

The AudVis sidebar's **VIRTUAL Bridge** panel connects Blender to VIRTUAL on
this computer. It sends OSC commands for tempo, A/B crossfader, master opacity,
blackout, freeze and eight scene launches. It requires no new Python packages.

In Blender's 3D Viewport, press **N**, select the **AudVis** sidebar tab, and
expand **VIRTUAL Bridge**. Blender 5.2 requires the
`audvis-8.0.1-blender5.2-macos-arm64.zip` extension build; installing a new
VIRTUAL executable does not update the Blender extension. After updating the
extension, restart Blender to load the new panel code.

VIRTUAL's operator editor has three session-only views: **Performance**,
**Audio**, and **Setup / Connections**. Performance opens by default, and
Show Mode returns to it. Master opacity, blackout, freeze and the A/B crossfader
remain above the scrolling editor in every view. Audio analysis and mapping
live in Audio; project, device, output and OSC settings live in Setup /
Connections. This first workspace pass keeps existing controller targets and
project formats; it does not introduce dockable panels or an independent
preview bus.

1. In Blender, open the bridge panel and click **Connect / Reconnect**. Defaults
   are VIRTUAL port `9000` and feedback port `9001`.
2. In VIRTUAL, choose **Setup / Connections**, expand setup and OSC input,
   listen on `127.0.0.1:9000`, set the feedback target to `127.0.0.1:9001`,
   then enable **Send feedback**. If feedback was already enabled, toggle it
   off and on to send a fresh state snapshot.
3. Confirm Blender says **Receiving VIRTUAL feedback**. UDP command delivery
   alone does not prove VIRTUAL received or accepted the command.
4. Assign an existing AudVis snapshot to each desired scene row. Click a
   numbered row button, or launch that scene from VIRTUAL, to recall the
   snapshot when its launch-request feedback arrives.
   Empty snapshot assignments do nothing.

Snapshot assignments and port settings are saved in the `.blend`. Connections
are session-only: file loading, extension disable or deleting the connected
scene closes the socket. Renaming the connected scene requires reconnecting.
Only one scene owns the connection at a time. Incoming snapshots target that
scene even if another scene becomes active. Snapshot morphs retain AudVis's
existing duration and parameter-only behavior; they do not switch Blender scenes.

The editable sliders are outgoing values, not feedback mirrors. Blackout and
freeze readouts and the reported VIRTUAL BPM reflect received state. No feedback
is echoed automatically, avoiding control loops. Silence does not prove a
connection is lost: feedback is event-driven and the panel shows its age.

## Timing and video limitations

VIRTUAL scene feedback acknowledges the **launch request**, before a quantized
clip necessarily starts. Use Immediate quantization for this first bridge;
beat/bar-aligned Blender cues need an execution-time cue protocol. UDP can lose
messages and is not an exactly-once transport. Repeated launch messages recall
the assigned snapshot again.

Sending BPM changes VIRTUAL's tempo only; it does not synchronize Blender phase
or select a Blender beat source. Use the existing MIDI clock facilities for
clock synchronization. This bridge does not transmit audio analysis or video.
VIRTUAL's existing NDI sender is program output, not a Blender input receiver.
Receiving Blender frames requires a separate source adapter. The next milestone
should prototype frame transport, then add execution-time cue messages and
shared macro identities before coordinated show saving.

## Viewport video stream prototype

The separate **VIRTUAL Viewport Stream** panel sends the selected 3D Viewport
to a VIRTUAL listener at `127.0.0.1:9010`. Start it explicitly from the target
3D Viewport; stopping it, loading a file, or disabling AudVis removes the draw
handler and closes the worker. Host, port and frame-rate controls are session
settings. Use **Measure only** to inspect readback cost and achieved capture
rate without opening a network socket. This stream carries video only and does
not use OSC.

The provisional TCP v1 framing is a 36-byte `!4sHHIIQQI` header (`VFRM`,
version 1, RGBA8 format 1, width, height, sequence, monotonic nanoseconds,
payload length), followed by tightly packed top-to-bottom RGBA8 pixels. The
sender caps output at 3840 × 2160 and 60 fps. It keeps only one pending frame;
the network thread connects and writes. A socket failure stops capture and
removes the draw handler. Blender's framebuffer readback still runs synchronously inside the viewport draw callback, so its
measured cost and color/orientation behavior must be checked on the target
Blender/GPU before treating these values as a stable protocol.

In VIRTUAL, choose **AudVis stream** for a deck and click **Listen** on port
9010, then start the sender in Blender. Listener and source state are session
only. The VIRTUAL receiver accepts localhost connections, validates dimensions
before allocating a frame, and routes RGBA frames through the deck's existing
live-frame path. Status includes connection, dimensions, received frames,
sender sequence gaps, local scheduler drops and time since the last complete
frame arrived.

The bridge binds only to loopback, consumes at most 32 datagrams of 4096 bytes
per timer tick, rejects malformed/unsupported packets, retains a fixed set of
readouts, and applies snapshots on Blender's main thread. It accepts immediate
numeric OSC messages; bundles are not supported on this feedback endpoint.

## Checks

```sh
python3 -m unittest tests.test_virtual_osc
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tests/blender_virtual_bridge_smoke.py
```

The smoke check uses temporary loopback sockets, validates command encoding,
feedback snapshot dispatch, packet limits, reconnect and file-load cleanup. It
does not validate drawn UI, a running VIRTUAL instance or physical MIDI devices.
