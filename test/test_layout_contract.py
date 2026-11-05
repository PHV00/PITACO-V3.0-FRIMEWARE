"""Contratos do layout do repositório após a reorganização PITACO 2.4."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "frimeware2.4"
BRIDGE = ROOT / "arduino-pitaco-mpx5010dp-ble"
LEGACY = ROOT / "arduino-pitaco-ble-legancy"
MODULES = (
    "sqi/gate_01_integrity.ino",
    "communication/pitaco_ble_ota.ino",
    "communication/pitaco_commands.ino",
    "processing/pitaco_ppg_bpm.ino",
    "processing/pitaco_ppg_contact_sqi.ino",
    "communication/pitaco_ppg_json.ino",
    "sensors/pitaco_ppg_sensor.ino",
    "sensors/pitaco_respiration.ino",
)


class LayoutContract(unittest.TestCase):
    def test_one_active_firmware_and_explicit_module_includes(self):
        self.assertEqual(SKETCH.name, "frimeware2.4")
        self.assertFalse((ROOT / "frimeware2.5").exists())
        main = (SKETCH / "frimeware2.4.ino").read_text(encoding="utf-8")
        self.assertEqual({p.name for p in SKETCH.glob("*.ino")}, {"frimeware2.4.ino"})
        for module in MODULES:
            with self.subTest(module=module):
                self.assertTrue((SKETCH / module).is_file())
                self.assertEqual(main.count('#include "' + module + '"'), 1)
        self.assertEqual(main.count("void setup() {"), 1)
        self.assertEqual(main.count("void loop() {"), 1)

    def test_local_driver_under_sketch_src(self):
        vendor = SKETCH / "src" / "vendor_sparkfun_max3010x"
        main = (SKETCH / "frimeware2.4.ino").read_text(encoding="utf-8")
        for filename in ("MAX30105.cpp", "MAX30105.h", "heartRate.cpp",
                         "heartRate.h", "README.md", "LICENSE.md"):
            self.assertTrue((vendor / filename).is_file(), filename)
        self.assertIn('src/vendor_sparkfun_max3010x/MAX30105.h', main)
        self.assertIn('src/vendor_sparkfun_max3010x/heartRate.h', main)

    def test_bridge_and_tools_import_paths(self):
        launcher = BRIDGE / "ble_client_mpx5010dp.py"
        self.assertIn("from pitaco_bridge.gui import run_gui",
                      launcher.read_text(encoding="utf-8"))
        self.assertTrue((BRIDGE / "pitaco_bridge" / "gui" / "main_window.py").is_file())
        self.assertTrue((BRIDGE / "pitaco_bridge" / "experimental.py").is_file())
        self.assertTrue((BRIDGE / "pitaco_experimental" / "pitaco24_ppg_probe.py").is_file())
        self.assertTrue((BRIDGE / "pitaco_experimental" / "analyze_ppg_25hz.py").is_file())

    def test_root_test_docs_requirements_and_legacy(self):
        self.assertTrue((ROOT / "requirements.txt").is_file())
        self.assertTrue((ROOT / "docs" / "firmware" / "GATE_01.md").is_file())
        self.assertTrue((ROOT / "test" / "test_sqi_gate1.cpp").is_file())
        self.assertTrue((LEGACY / "arduino-pitaco-ble-legancy.ino").is_file())


if __name__ == "__main__":
    unittest.main()
