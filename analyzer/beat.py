"""Tempo and onset tracking, independent of Blender. Times are seconds."""
from collections import deque
from statistics import median
import math


class MidiClock:
    """24 ticks per quarter note, with transport and loss detection."""
    def __init__(self):
        self.ticks = deque(maxlen=97)
        self.running = False
        self.count = 0
        self.origin = None

    def receive(self, message, now):
        if message == 'start':
            self.ticks.clear()
            self.count = 0
            self.origin = now
            self.running = True
        elif message == 'continue':
            self.running = True
        elif message == 'stop':
            self.running = False
        elif message == 'clock':
            if self.ticks and now <= self.ticks[-1]:
                return
            if self.ticks and now - self.ticks[-1] > .5:
                self.ticks.clear()
            self.ticks.append(now)
            if self.running:
                self.count += 1

    def bpm(self, now):
        if len(self.ticks) < 25 or now - self.ticks[-1] > .5:
            return None
        dt = self.ticks[-1] - self.ticks[0]
        return 60 * (len(self.ticks) - 1) / (24 * dt) if dt > 0 else None


class BeatTracker:
    def __init__(self):
        self.bpm = 120.0
        self.origin = None
        self.previous = None
        self.flux = deque()
        self.onsets = deque()
        self.taps = deque(maxlen=8)
        self.onset_count = 0
        self.last_onset = -math.inf
        self.last_time = None
        self.counter = 0
        self.phase = self.bar = self.pulse = self.onset = 0.0

    def tap(self, now):
        if self.taps and now - self.taps[-1] > 2:
            self.taps.clear()
        if self.taps and now <= self.taps[-1]:
            return
        self.taps.append(now)
        if len(self.taps) > 1:
            self.bpm = 60 / median([b-a for a,b in zip(self.taps, list(self.taps)[1:]) if b > a])
        self.origin = now
        self.update(now, tempo=self.bpm)

    def update(self, now, energies=None, sensitivity=1.5, bpm_min=60, bpm_max=180, tempo=None, running=True):
        if self.last_time is not None and now < self.last_time:
            self.__init__()
        self.last_time = now
        self.onset = 0.0
        if energies is not None:
            bands = [math.log1p(max(0, x)) for x in energies]
            flux = sum(max(0, x-y) for x,y in zip(bands, self.previous or bands))
            self.previous = bands
            while self.flux and self.flux[0][0] < now - 1:
                self.flux.popleft()
            threshold = max(1e-7, median([x[1] for x in self.flux]) * sensitivity) if self.flux else 1e-7
            if flux > threshold and now - self.last_onset >= .1:
                self.last_onset = now
                self.onset_count += 1
                self.onset = 1.0
                self.onsets.append(now)
                while self.onsets and self.onsets[0] < now - 8:
                    self.onsets.popleft()
                if len(self.onsets) > 1:
                    intervals = [b-a for a,b in zip(self.onsets, list(self.onsets)[1:])]
                    candidate = 60 / median(intervals)
                    while candidate < bpm_min: candidate *= 2
                    while candidate > bpm_max: candidate /= 2
                    if bpm_min <= candidate <= bpm_max:
                        self.bpm += (candidate-self.bpm) * .25
                if self.origin is None:
                    self.origin = now
                else:
                    number = round(max(0, (now-self.origin)*self.bpm/60))
                    self.origin = now - number*60/self.bpm
            self.flux.append((now, flux))
        if tempo is not None and tempo > 0:
            self.bpm = tempo
        if self.origin is None:
            self.origin = now
        beats = max(0, (now-self.origin) * self.bpm / 60)
        if running:
            self.counter = int(beats)
        self.phase = beats % 1 if running else 0.0
        self.bar = (beats % 4) / 4 if running else 0.0
        self.pulse = float(running and self.phase < .15)
        return self

    def output(self, name):
        return {'pulse': self.pulse, 'phase': self.phase, 'bar': self.bar,
                'bpm': self.bpm, 'onset': self.onset}.get(name, 0.0)
