"""Beat math, without Blender or numpy."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('beat', Path(__file__).resolve().parents[1] / 'analyzer/beat.py')
beat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(beat)

class BeatTests(unittest.TestCase):
    def test_click_train(self):
        t = beat.BeatTracker()
        for i in range(480):
            t.update(i/60, [1.0 if i % 30 == 0 else 0.0] * 16)
        self.assertAlmostEqual(t.bpm, 120, delta=2)
        self.assertGreater(t.onset_count, 12)
        t.update(8.25, [0]*16)
        self.assertAlmostEqual(t.phase, .5, places=5)

    def test_tap(self):
        t = beat.BeatTracker()
        for now in (10, 10.5, 11, 11.5): t.tap(now)
        self.assertEqual(t.bpm, 120)
        t.update(11.75, tempo=t.bpm)
        self.assertAlmostEqual(t.phase, .5)

    def test_clock_and_transport(self):
        c = beat.MidiClock()
        c.receive('start', 0)
        for i in range(97): c.receive('clock', i/48)
        self.assertAlmostEqual(c.bpm(2), 120)
        self.assertTrue(c.running)
        c.receive('stop', 2)
        self.assertFalse(c.running)
        c.receive('continue', 2.1)
        self.assertTrue(c.running)
        self.assertIsNone(c.bpm(3))

    def test_transport_loss_freezes_counter(self):
        t = beat.BeatTracker()
        t.update(0, tempo=120)
        t.update(2, tempo=120)
        counter = t.counter
        t.update(10, running=False)
        self.assertEqual(t.counter, counter)
        self.assertEqual(t.pulse, 0)

    def test_rewind_and_silence(self):
        t = beat.BeatTracker()
        for i in range(100): t.update(i/24, [0]*16)
        self.assertEqual(t.onset_count, 0)
        t.update(0, [0]*16)
        self.assertEqual(t.phase, 0)
        self.assertEqual(t.counter, 0)

if __name__ == '__main__': unittest.main()
