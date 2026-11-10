"""Protocol checks without Blender or third-party dependencies."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('virtual_osc', Path(__file__).resolve().parents[1] / 'analyzer/virtual_osc.py')
osc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(osc)


class VirtualOscTests(unittest.TestCase):
    def test_virtual_feedback_numeric_types(self):
        raw = osc.encode('/virtual/tempo', 128)
        self.assertEqual(osc.decode(raw), ('/virtual/tempo', 128))
        prefix = raw[:-8]
        for tag, data, expected in [(b',i\0\0', struct.pack('>i', 120), 120),
                                    (b',d\0\0', struct.pack('>d', .25), .25),
                                    (b',T\0\0', b'', 1), (b',F\0\0', b'', 0)]:
            self.assertEqual(osc.decode(prefix + tag + data)[1], expected)

    def test_malformed_and_nonfinite_rejected(self):
        raw = osc.encode('/virtual/tempo', 120)
        for packet in [b'', raw[:-1], raw + b'\0'*4, b'X'*4096,
                       b'#bundle\0'+b'\0'*8, raw[:-4]+struct.pack('>f', float('nan')),
                       raw[:-4]+struct.pack('>f', float('inf')), b'X'*4100,
                       b'/other\0\0,f\0\0'+struct.pack('>f', 1)]:
            with self.subTest(packet=packet[:24]), self.assertRaises(ValueError):
                osc.decode(packet)

    def test_scene_cues_only_accept_launch_edges(self):
        for i in range(1, 9):
            self.assertEqual(osc.scene_cue(f'/virtual/scene/{i}/launch', 1), i-1)
        for address in ['/virtual/scene/0/launch', '/virtual/scene/9/launch',
                        '/virtual/deck/1/level', '/virtual/scene/01/launch',
                        '/virtual/scene/1/launch/extra']:
            self.assertIsNone(osc.scene_cue(address, 1))
        self.assertIsNone(osc.scene_cue('/virtual/scene/1/launch', 0))

    def test_encoder_rejects_bad_address_and_nan(self):
        for address, value in [('/other/tempo', 1), ('/virtual/tempo\0hidden', 1),
                               ('/virtual/tempo', float('nan'))]:
            with self.assertRaises(ValueError):
                osc.encode(address, value)


if __name__ == '__main__':
    unittest.main()
