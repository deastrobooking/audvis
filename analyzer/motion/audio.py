"""Audio sampling shared by the Motion FX effects.

Every effect asks for one value per element (cascade copy, orbiting satellite...).
Values can be spread across elements by frequency band or by time delay, and are
smoothed with attack / release so motion reacts on hits and settles afterwards.
"""


def _band(props, i):
    if props.spread == 'bands':
        low = props.freq_start + i * props.freq_step
    else:
        low = props.freq_start
    return low, low + props.freq_width


def sample_raw(props, driver, i):
    """Raw (unsmoothed) value for element i, already multiplied by props.factor."""
    if props.source == 'off':
        return 0.0
    if props.source == 'midi':
        note = props.midi_note + (i if props.spread == 'bands' else 0)
        val = driver(midi=note,
                     ch=props.midi.channel,
                     track=props.midi.track,
                     file=props.midi.file,
                     device=props.midi.device)
    else:
        kwargs = {}
        if props.sound_sequence != '':
            kwargs['seq'] = props.sound_sequence
        if props.sequence_channel > 0:
            kwargs['seq_channel'] = props.sequence_channel
        low, high = _band(props, i)
        val = driver(low, high, ch=props.channel, **kwargs)
    return val * props.factor


class MotionAudio:
    def __init__(self):
        self._smoothed = {}  # key -> (frame, [values])
        self._history = {}  # key -> {frame: value}
        self._accumulated = {}  # key -> (frame, value)

    def reset(self):
        self._smoothed.clear()
        self._history.clear()
        self._accumulated.clear()

    def values(self, key, props, driver, count, scene, frame):
        """One smoothed value per element. Smoothing restarts whenever the frame
        doesn't follow the previous one (scrubbing, jumps), so rendering is
        reproducible from the first rendered frame on."""
        if props.spread == 'delay':
            raw = self._delayed(key, props, driver, count, scene, frame)
        else:
            raw = [sample_raw(props, driver, i) for i in range(count)]
        last = self._smoothed.get(key)  # (frame, values smoothed from, smoothed values)
        if last is not None and last[0] == frame:
            base = last[1]  # same frame again (settings changed while paused): redo, don't smooth twice
        elif last is not None and 0 < frame - last[0] <= 1:
            base = last[2]
        else:
            base = None
        if base is None or len(base) != count:
            base = None
            out = raw
        else:
            out = []
            for prev, cur in zip(base, raw):
                speed = props.attack if cur > prev else props.release
                out.append(prev + (cur - prev) * speed)
        self._smoothed[key] = (frame, base, out)
        return out

    def _delayed(self, key, props, driver, count, scene, frame):
        history = self._history.setdefault(key, {})
        current = sample_raw(props, driver, 0)
        history[frame] = current
        window = count * props.delay + 2
        if len(history) > window * 4 + 100:
            for f in [f for f in history if f < frame - window]:
                del history[f]
        out = []
        for i in range(count):
            f = frame - i * props.delay
            if f in history:
                out.append(history[f])
            elif f < scene.frame_start:
                out.append(0.0)  # before the song starts: silence
            else:
                out.append(current)  # not played through yet (scrubbing)
        return out

    def accumulate(self, key, amount, scene, frame):
        """Running sum of amount per frame, restarting at the scene's first frame.
        Used to push orbits forward by sound without jumps."""
        last = self._accumulated.get(key)
        if last is None or frame <= scene.frame_start:
            value = 0.0
        elif last[0] == frame:
            return last[1]
        elif 0 < frame - last[0] <= 1:
            value = last[1] + amount * (frame - last[0])
        else:
            value = last[1]
        self._accumulated[key] = (frame, value)
        return value
