import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "arduino-pitaco-mpx5010dp-ble"))
from pitaco_bridge.protocol import BleJsonlBuffer, parse_pitaco_line


def frame(seq=7):
    return {"type": "sample", "seq": seq, "t_ms": 10220,
            "ppg": {"red": 105000, "ir": 119000, "bpm": 74.2, "bpm_valid": True},
            "mpx5010dp": {"pressure_pa": -24.8, "valid": True},
            "sqi": {"g1": True, "reason": 0}}


class ProtocolTests(unittest.TestCase):
    def test_legacy_pressure(self):
        self.assertEqual(parse_pitaco_line("14.50")["mpx5010dp"]["pressure_pa"], 14.5)

    def test_invalid_legacy(self):
        self.assertIsNone(parse_pitaco_line("nan"))

    def test_json_sample(self):
        self.assertEqual(parse_pitaco_line(json.dumps(frame()))["ppg"]["ir"], 119000)

    def test_json_g1(self):
        msg = '{"type":"g1","window":1,"sqi":{"g1":false,"reason":2}}'
        self.assertFalse(parse_pitaco_line(msg)["sqi"]["g1"])

    def test_reject_over_range(self):
        data = frame()
        data["ppg"]["red"] = 262144
        self.assertIsNone(parse_pitaco_line(json.dumps(data)))

    def test_ble_fragments(self):
        stream = (json.dumps(frame(7)) + "\n" + json.dumps(frame(8)) + "\n").encode()
        acc = BleJsonlBuffer()
        result = []
        for i in range(0, len(stream), 20):
            result.extend(acc.feed(stream[i:i + 20]))
        self.assertEqual([parse_pitaco_line(x)["seq"] for x in result], [7, 8])

    def test_ble_short_frames(self):
        acc = BleJsonlBuffer()
        self.assertEqual(acc.feed(b'{"type":"'), [])
        self.assertEqual(acc.feed(b'bad"}\n'), ['{"type":"bad"}'])
        self.assertIsNone(parse_pitaco_line('{"type":"bad"}'))

    def test_ble_overflow(self):
        acc = BleJsonlBuffer(max_line_bytes=40)
        acc.feed(b"x" * 41)
        self.assertEqual(acc.feed(b"\n"), [""])
        self.assertIsNone(parse_pitaco_line(""))


if __name__ == "__main__":
    unittest.main()
