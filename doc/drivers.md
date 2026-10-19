# Drivers

You can animate many, many things by writing your own drivers. Just right click on any numeric value, for example
object's Location X, and click "Add Driver". Then write any expression.

Simplest formula looks like this: `audvis(100, 200)` - this will animate your property by sound frequencies 100Hz -
200Hz.

## Python driver expressions

You want to read the manual [here](https://docs.blender.org/manual/en/latest/animation/drivers/drivers_panel.html),
[here](https://docs.blender.org/manual/en/latest/animation/drivers/introduction.html)
and [especially here](https://docs.blender.org/manual/en/latest/animation/drivers/drivers_panel.html#drivers-simple-expressions)
.

Here are some simple expressions to show what you probably want to do:

- `audvis(100, 200) * 10 + 100`
- `3 - audvis(100, 200) / 15`
- `clamp(audvis(100, 200) / 3, 0, 3)`

## Expressions for Realtime and Sequence analyzers:

- **seq** - `audvis(100, 200, seq="MyGreatSong.mp3")` - only react to MyGreatSong.mp3
- **ch** - `audvis(100, 200, ch=2)` - channel. By default, only one channel is parsed, so if you want to use more of
  them, you need to increase the value of `Channels Count` property in the main AudVis panel
- **seq** and **ch** can be combined - `audvis(100, 200, seq="MyGreatSong.mp3", ch=2)`

## Expressions for MIDI File and MIDI Realtime analyzers:

- **midi** - `audvis(midi=1)` - note 1. This parameters is needed if you want to use any midi, or
- **midi** - `audvis(midi=[40, 50])` - max. value from notes 40-50
- **midi** - `audvis(midi=[40, 50, 'avg'])` - average value from notes 40-50 
- **midi** - `audvis(midi=[40, 50, 'avg_nonzero'])` - average of non-zero values from notes 40-50 
- **midi** - `audvis(midi=[40, 50, 'sum'])` - sum of values from notes 40-50 
- **cc** - `audvis(cc=7)` - knob / fader CC 7 of MIDI Realtime as **0..1**, not changed by the Driver Values
  settings (`midi_control=7` gives the raw value scaled like sound). Works with **ch** and **device**
- **device** - `audvis(midi=1, device="MIDI Device 1")` - name of the device from the MIDI Realtime panel
- **ch** - `audvis(midi=1, ch="1")` - midi channel
- **file** - `audvis(midi=3, file='MyGreatSong.mid')` - file name from the MIDI File panel
- **track** - `audvis(midi=3, file='MyGreatSong.mid', track='Track 1')` - track from the file. If your tracks in the
  MIDI are not named, they will get names like "Track 1"
- you can combine **device** + **ch**, or **file** + **track** + **ch**, but **device** + **file** makes absolutely no
  sense.

## Some ideas what to animate with drivers:

- object's basic properties like location, rotation, scale
- shape key value
- array modifier's Count property
- `Object -> Viewport Display -> Color` and use it inside shading nodes`
- armature bones' properties - rotation and/or scale or event Bone Constraints
- light color / power / radius...
- camera focal length
- almost any nodes in geometry nodes, shading, compositing...
- depth of field settings
- just experiment! Explore all the possibilities (impossible) and have fun
## Beat outputs and Sound Links

The **Beat** sidebar panel selects Audio, MIDI Clock, or Tap as the tempo source. Driver expressions:

```python
audvis(beat='pulse')  # short 0/1 beat pulse
audvis(beat='phase')  # quarter-note phase, 0..1
audvis(beat='bar')    # four-beat bar phase, 0..1
audvis(beat='bpm')    # tempo in beats per minute
audvis(beat='onset')  # 1 on a detected audio onset frame
```

These outputs bypass Driver Values scaling. Audio onset detection compares positive spectral
flux across 16 log-spaced bands against an adaptive median threshold, with a 100 ms refractory
period. Tempo uses recent onset intervals within the configured BPM range. Detection is sampled
once per frame: low frame rates and complex rhythms reduce accuracy. File audio uses timeline
time; live audio, MIDI Clock and Tap use monotonic time. Seeking backward resets audio tracking;
play from the start to establish tempo. Live tempo is not a recording of your performance.

To link sound without typing a driver, enter **Map Mode**, arm a numeric property, then click
one of the band 1–8 buttons or **Beat pulse / Beat phase / Bar phase**. The new mapping uses
Range, Curve, Invert, Smoothing and Record from MIDI Mappings. Sound links work with MIDI
Realtime disabled and run in the frame handler before Motion FX, including during rendering.
Map Mode can start with MIDI Realtime disabled for sound-only linking.
EQ levels include the band's gain and use the same 0..1 scale as the meters. Sound sources have
no MIDI device/channel filtering. Band sources use numbers 1–8; beat sources use 0–2.

Smoothing retains frame history during forward playback and resets on seeks; it is not an
arbitrary-order animation cache. Use zero smoothing for direct frame-independent EQ links,
or Record/bake the result of sequential playback. Multiple mappings to one property compete;
use one active source per target. A property with a driver or f-curve can override a link, as
shown by the mapping status message.
