"""Testa contrato Python->Unity sem hardware, Unity ou Tk."""
import math
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pitaco_bridge.game_output import (
    GAME_OUTPUT_PRESSURE, GAME_OUTPUT_FLOW, GAME_OUTPUT_COMBO, build_game_frame
)


def ppg(bpm=72.5, age=.2, g1=True, contact=True, experimental=None):
    return {"bpm": bpm, "sample_age_s": age,
            "g1_effective": g1, "contact": contact,
            "experimental": experimental or {"spo2": 97.0, "bpm": 76.0}}


class CombinedGameOutputTest(unittest.TestCase):
    def test_preserves_numeric_legacy_modes(self):
        self.assertEqual(build_game_frame(-28.487, GAME_OUTPUT_PRESSURE), b"-28.49\r\n")
        self.assertEqual(build_game_frame(18.24, GAME_OUTPUT_FLOW), b"18.24\r\n")

    def test_combined_one_line_single_receiver(self):
        self.assertEqual(build_game_frame(-23.147, GAME_OUTPUT_COMBO, ppg()),
                         b"P24,-23.15,72.5,,1,1\r\n")

    def test_no_spo2_demo_even_if_present(self):
        frame = build_game_frame(21, GAME_OUTPUT_COMBO, ppg(experimental={"spo2":98.4}))
        self.assertEqual(frame, b"P24,21.00,72.5,,1,1\r\n")
        self.assertNotIn(b"98.4", frame)

    def test_missing_bpm_is_not_zero(self):
        self.assertEqual(build_game_frame(20, GAME_OUTPUT_COMBO, ppg(bpm=None)),
                         b"P24,20.00,,,1,1\r\n")

    def test_gate_or_contact_rejects_bpm(self):
        self.assertEqual(build_game_frame(20, GAME_OUTPUT_COMBO, ppg(g1=False)),
                         b"P24,20.00,,,0,1\r\n")
        self.assertEqual(build_game_frame(20, GAME_OUTPUT_COMBO, ppg(contact=False)),
                         b"P24,20.00,,,1,0\r\n")

    def test_stale_or_missing_snapshot_invalidates_biosignals(self):
        self.assertEqual(build_game_frame(20, GAME_OUTPUT_COMBO, ppg(age=2)),
                         b"P24,20.00,,,0,0\r\n")
        self.assertEqual(build_game_frame(20, GAME_OUTPUT_COMBO),
                         b"P24,20.00,,,0,0\r\n")

    def test_invalid_sensor_value_fails_closed(self):
        with self.assertRaises(ValueError):
            build_game_frame(math.nan, GAME_OUTPUT_COMBO, ppg())

    def test_frame_has_fixed_six_columns(self):
        for snap in (None, ppg(), ppg(bpm=None), ppg(age=9)):
            parts = build_game_frame(0, GAME_OUTPUT_COMBO, snap).decode("ascii").strip().split(",")
            self.assertEqual(len(parts), 6)
            self.assertEqual(parts[0], "P24")
            self.assertEqual(parts[3], "")


if __name__ == "__main__":
    unittest.main()
