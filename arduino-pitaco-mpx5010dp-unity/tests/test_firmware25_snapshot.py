"""Teste de paridade do sketch canonico 2.4 com snapshot 2.5."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "arduino-pitaco-mpx5010dp-unity" / "firmware" / "pitaco_2_4"
VERSION25 = ROOT / "frimeware2.5"
TABS = ["pitaco_2_4.ino","gate_01_integrity.ino","pitaco_ble_ota.ino","pitaco_commands.ino","pitaco_ppg_bpm.ino","pitaco_ppg_contact_sqi.ino","pitaco_ppg_json.ino","pitaco_ppg_sensor.ino","pitaco_respiration.ino"]
VENDOR = ["src/vendor_sparkfun_max3010x/LICENSE.md","src/vendor_sparkfun_max3010x/MAX30105.cpp","src/vendor_sparkfun_max3010x/MAX30105.h","src/vendor_sparkfun_max3010x/README.md","src/vendor_sparkfun_max3010x/heartRate.cpp","src/vendor_sparkfun_max3010x/heartRate.h"]


class Firmware25Parity(unittest.TestCase):
    def test_primary_file_matches_folder(self):
        self.assertTrue((ORIGINAL / "pitaco_2_4.ino").is_file())
        self.assertTrue((VERSION25 / "frimeware2.5.ino").is_file())

    def test_all_soc_tabs_unchanged(self):
        for name in TABS:
            other = "frimeware2.5.ino" if name == TABS[0] else name
            with self.subTest(name=name):
                self.assertEqual((ORIGINAL / name).read_bytes(),
                                 (VERSION25 / other).read_bytes())

    def test_sparkfun_vendor_unchanged(self):
        for name in VENDOR:
            with self.subTest(name=name):
                self.assertEqual((ORIGINAL / name).read_bytes(),
                                 (VERSION25 / name).read_bytes())

    def test_docs_available(self):
        for name in ("README.md", "docs/SOC_INO_TABS.md", "docs/GATE_01.md"):
            self.assertTrue((VERSION25 / name).is_file())


if __name__ == "__main__":
    unittest.main()
