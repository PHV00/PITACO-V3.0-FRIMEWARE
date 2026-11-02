"""Verifica formatos de telemetria MAX30105 (sem sensor)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pitaco24_ppg_probe import parse_usb_record


class Max30105ProtocolTest(unittest.TestCase):
    def test_red_ir_default(self):
        self.assertEqual(parse_usb_record("R,1,1200,8,109840,122963"),
                         ("R", 1, 1200, 8, 109840, 122963, None))

    def test_green_optional(self):
        self.assertEqual(parse_usb_record("R,2,1240,8,109840,122963,120100"),
                         ("R", 2, 1240, 8, 109840, 122963, 120100))

    def test_quality_independent_of_green(self):
        self.assertEqual(parse_usb_record("Q,8,6200,0,2,125"),
                         ("Q", 8, 6200, 0, 2, 125))

    def test_pressure_legacy(self):
        self.assertEqual(parse_usb_record("-24.50"), ("P", -24.5))

    def test_status(self):
        val = "X,PPG_READY,MAX30105,CHANNELS,RED_IR_GREEN,G1_ONLY"
        self.assertEqual(parse_usb_record(val), ("X", val))

    def test_overflow_raw(self):
        self.assertIsNone(parse_usb_record("R,3,1400,8,262144,100000"))

    def test_corrupt(self):
        self.assertIsNone(parse_usb_record("R,0,abc,8,100000,120000"))


if __name__ == "__main__":
    unittest.main()
