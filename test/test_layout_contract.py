"""Invariantes de localizacao após a reorganizacao de pastas do PITACO."""
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SKETCH = PROJECT / "firmware" / "pitaco_2_4"
TABS = {
    "pitaco_2_4.ino", "pitaco_ble_ota.ino", "pitaco_commands.ino",
    "pitaco_ppg_json.ino", "pitaco_ppg_bpm.ino",
    "pitaco_ppg_contact_sqi.ino", "pitaco_ppg_sensor.ino",
    "pitaco_respiration.ino", "gate_01_integrity.ino",
}


class LayoutContract(unittest.TestCase):
    def test_sketch_has_arduino_root_and_tabs(self):
        self.assertEqual({p.name for p in SKETCH.glob("*.ino")}, TABS)
        self.assertEqual(SKETCH.name, "pitaco_2_4")
        main = (SKETCH / "pitaco_2_4.ino").read_text(encoding="utf-8")
        self.assertIn('src/vendor_sparkfun_max3010x/MAX30105.h', main)
        self.assertIn('src/vendor_sparkfun_max3010x/heartRate.h', main)

    def test_local_driver_is_within_sketch_src(self):
        vendor = SKETCH / "src" / "vendor_sparkfun_max3010x"
        for filename in ("MAX30105.cpp", "MAX30105.h", "heartRate.cpp",
                         "heartRate.h", "README.md", "LICENSE.md"):
            with self.subTest(filename=filename):
                self.assertTrue((vendor / filename).is_file())

    def test_python_entrypoints_and_research_paths(self):
        launch = PROJECT / "ble_client_mpx5010dp.py"
        self.assertIn("from pitaco_bridge.gui import run_gui",
                      launch.read_text(encoding="utf-8"))
        research = PROJECT / "pitaco_experimental"
        for filename in ("analyze_ppg_25hz.py", "pitaco24_ppg_probe.py"):
            self.assertTrue((research / filename).is_file())

    def test_legacy_25_snapshot_kept_outside_primary_sketch(self):
        self.assertTrue((PROJECT.parent / "frimeware2.5" / "frimeware2.5.ino").is_file())


if __name__ == "__main__":
    unittest.main()
