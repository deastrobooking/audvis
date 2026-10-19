# MIDI Realtime

Play your MIDI controller into Blender: map knobs, faders and pads to any value (AudVis or Blender's own), or use
notes and controls in driver expressions. Add your controller in the **Midi Realtime** panel and enable it in the
panel header.

## MIDI Mappings (map knobs, faders and pads)

1. Enable **Midi Realtime** and add your controller (**Add Midi Input**, pick the **Input Device**).
2. Click **Map Mode** (top of the Midi Realtime panel).
3. **Click any value** in Blender - an object's Location X, a light's Power, a material or Geometry Nodes input,
   the Motion FX **Master** or an effect's **Influence**, an EQ gain. Dragging or typing a new value works too.
   The panel and the status bar show what is armed.
4. Move a knob or fader, or hit a pad. Done - it's in the **MIDI Mappings** list.
5. Repeat 3-4 for the next value. Click **Map Mode** again or press **Esc** when you're done.

Mapping a value again replaces its knob. Without Map Mode you can also right-click a value > **AudVis: MIDI Learn**.

Mappings work while playing and while paused, in every scene of the file. In the list, select a mapping to tune it:

- **Type / Number / Ch / Device** - which control. The eyedropper re-learns it. Channel 0 and an empty Device
  mean any. Device takes the name from the input list above (or the hardware name)
- **Data Path** - the mapped value. You can also paste one: right-click a value > **Copy Full Data Path**. Pick one
  component (Location **X**), not a whole vector
- **Response**
    - *Fader / Knob* - follow the knob from **Min** to **Max**. Pads: velocity while held
    - *Hold* - Max while a pad is held, Min when released
    - *Toggle* - each press switches between Min and Max (checkboxes default to this). CC buttons work too
- **Min / Max** - the range, preset from the value's slider range. Swap them, or use **Invert**, to turn the knob
  around. Dropdowns step through their items
- **Curve** - 1 = linear, higher = finer control at the low end
- **Smoothing** - glide to the knob instead of jumping
- **Pickup** - don't jump when the value was changed elsewhere (mouse, another scene): the knob takes over once it
  reaches the current value
- **Record** - while playing, insert keyframes as you move the knob: record an automation pass

A value with keyframes or a driver is marked in the list: keyframes and drivers win on the next frame, so use
**Record**, remove them, or map the Motion FX **Influence** instead.

**Actions** (the play button next to the list): a pad or CC button can **Play / Pause**, go to the **Next /
Previous Scene** or a chosen scene (like the Scenes grid), or **Engage / Release / Stop** all Motion FX. Set the
note with the eyedropper.

## Usage in driver expressions:

You can combine parameters, but combining midi=30 (note) and midi_control=83 (control) doesn't make sense
- `audvis(midi=30)` - midi note 30
- `audvis(midi=30, ch=3)` - channel 3
- `audvis(midi=30, device="My cool midi device")` - only midi notes from this device
- `audvis(cc=83)` - knob / fader 83 as 0..1 (not affected by the Driver Values settings)
- `audvis(midi_control=83)` - raw 0..127, scaled by the Driver Values settings like sound

Drivers only update when the frame changes. For knobs that should also work while paused, use MIDI Mappings.

## Settings

- **Enable** (in the Midi Realtime panel header): do you want to use Midi Realtime feature? If not, keep this disabled
- checkbox inside the list of inputs: enable / disable single device 
- **Add Midi Input**: adds midi input
- **Name**: Name to refer in driver expressions
- **Input Device**: select the device connected to your computer
- **Restart Midi Inputs**: restarts the backend. Use when in trouble
- **Debug Realtime Midi Messages**: write last midi note / midi control message in the workspace status text (left
  bottom corner)

## MIDI Learn

You don't need to look up CC numbers. With MIDI Realtime enabled, click **Learn** in a Motion FX
[MIDI CC Control](./motion.md#live-controls-midi-cc) box, or **Map** under an
[EQ / Macros](./motion.md#eq--macros) gain slider, then move a knob or fader. Esc cancels; after 15 seconds
without a message it cancels by itself, and it also cancels if MIDI Realtime is switched off while waiting.

## Clock, profiles, bank fill and monitor

MIDI Clock, Start, Stop and Continue are received separately from controller messages. Select
**Beat > Source > MIDI Clock** to use 24 ticks per quarter note; Start resets the beat count,
Stop suppresses pulses, and Continue resumes. Tempo becomes available after 24 tick intervals
and is unavailable after half a second without a tick. Clock messages do not trigger Learn or
Map Mode. If several devices provide clocks, the first valid clock supplies both tempo and
transport; enable only the intended clock input for a show. **Tap Tempo** switches to Tap;
you can also map the **Tap Tempo** action to a pad or CC button.

**MIDI Mappings > Export Profile** saves a versioned JSON file with every mapping setting.
**Import Profile** appends by default; enable **Replace Existing** in the file browser to replace
all mappings in this scene. Imported mappings receive fresh runtime IDs. Object and scene names
are kept as data paths: when importing into another blend file, inspect **Target not found**
statuses and update paths. Profiles include sound links and snapshot actions, but do not contain
the snapshots themselves or controller device setup.

Learn fader 1 onto `eq_band_1.gain`, select that mapping, then choose **Fill Bank**, Bank Size 8.
This keeps the first mapping and adds seven copies, incrementing both the MIDI number and the
last integer in the property path. Array components such as `[0]` also work. Missing targets
and MIDI numbers above 127 are skipped. Bank Size includes the selected control.

The **MIDI Monitor** at the bottom of MIDI Realtime displays the eight most recent note/CC
messages, including type, number, value, channel and device. It does not include timing ticks.
The **Recall Snapshot** action has a snapshot selector; snapshots belong to the mapping's scene.
