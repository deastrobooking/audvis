# MIDI Realtime

## Usage in driver expressions:

You can combine parameters, but combining midi=30 (note) and midi_control=83 (control) doesn't make sense
- `audvis(midi=30)` - midi note 30
- `audvis(midi=30, ch=3)` - channel 3
- `audvis(midi=30, device="My cool midi device")` - only midi notes from this device
- `audvis(midi_control=83)`

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
