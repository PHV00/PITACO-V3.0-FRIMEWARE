import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "arduino-pitaco-mpx5010dp-ble"))
"""Contrato da identificacao C e preservacao de RED/IR para a Unity."""
import json
import unittest

from pitaco_bridge.game_protocol import (
    GAME_OUTPUT_PITACO24_JSON, PITACO24_ECHO, encode_pitaco24_json,
    route_combo_unity_command,
)


class Pitaco24GameProtocolTest(unittest.TestCase):
    def test_handshake_is_exclusive(self):
        self.assertEqual(PITACO24_ECHO, b"echo2.4p\r\n")
        self.assertNotIn(b"echop", PITACO24_ECHO)
        self.assertNotIn(b"echox", PITACO24_ECHO)
        self.assertEqual(GAME_OUTPUT_PITACO24_JSON, "PITACO 2.4 (JSON)")

    def test_sample_preserves_pressure_red_ir_sequence(self):
        frame = {"type": "sample", "seq": 17, "t_ms": 4500,
                 "ppg": {"red": 12551, "ir": 18822, "bpm": None},
                 "mpx5010dp": {"pressure_pa": -23.15, "valid": True},
                 "sqi": {"g1": True, "contact": True}}
        raw = json.dumps(frame, separators=(",", ":"))
        result = encode_pitaco24_json(raw)
        self.assertEqual(result, raw.encode("ascii") + b"\r\n")
        self.assertEqual(json.loads(result), frame)

    def test_g1_event_preserved(self):
        self.assertEqual(encode_pitaco24_json(
            '{"type":"g1","t_ms":5000,"sqi":{"g1":true}}'),
            b'{"type":"g1","t_ms":5000,"sqi":{"g1":true}}\r\n')

    def test_rejects_legacy_and_invalid(self):
        for raw in ("-23.15", "X,PPG_READY", "{bad", "{}", "[]",
                    '{"type":"sample","seq":1,"ppg":{"red":12}}',
                    '{"type":"sample","seq":1,"ppg":{"red":12,"ir":13}}\n{"type":"g1"}',
                    "é"):
            self.assertIsNone(encode_pitaco24_json(raw), raw)


    def test_handshake_is_answered_in_bridge_only(self):
        reply, forwarded = route_combo_unity_command(b"e")
        self.assertEqual(reply, b"echo2.4p\r\n")
        self.assertEqual(forwarded, b"")
        self.assertEqual(route_combo_unity_command(b"r\n"), (None, b"r\n"))
        self.assertEqual(route_combo_unity_command(b"er\n"),
                         (PITACO24_ECHO, b"r\n"))
        self.assertEqual(route_combo_unity_command(b"f"), (None, b"f"))

if __name__ == "__main__":
    unittest.main()
