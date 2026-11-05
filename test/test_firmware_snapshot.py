"""Valida o código firmware e a biblioteca SparkFun após retirada da versão 2.5 duplicada.

Este teste substitui a antiga comparação de duas árvores completas.
O histórico da versão 2.5 continua recuperável pelo Git, sem cópia viva.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "frimeware2.4"
SOURCE_FILES = [
    "frimeware2.4.ino",
    "sqi/gate_01_integrity.ino",
    "communication/pitaco_ble_ota.ino",
    "communication/pitaco_commands.ino",
    "communication/pitaco_ppg_json.ino",
    "processing/pitaco_ppg_bpm.ino",
    "processing/pitaco_ppg_contact_sqi.ino",
    "sensors/pitaco_ppg_sensor.ino",
    "sensors/pitaco_respiration.ino",
]
VENDOR = [
    "LICENSE.md", "MAX30105.h", "MAX30105.cpp",
    "heartRate.h", "heartRate.cpp", "README.md",
]


class FirmwareSourceTests(unittest.TestCase):
    def test_no_missing_modules_and_no_duplicate_sketch(self):
        for name in SOURCE_FILES:
            with self.subTest(name=name):
                self.assertTrue((SKETCH / name).is_file())
        self.assertFalse((ROOT / "frimeware2.5").exists())

    def test_sparkfun_local_unmodified_runtime_files_present(self):
        vendor = SKETCH / "src" / "vendor_sparkfun_max3010x"
        for name in VENDOR:
            with self.subTest(name=name):
                self.assertTrue((vendor / name).is_file())
        hdr = (vendor / "MAX30105.h").read_text(encoding="utf-8")
        self.assertIn("STORAGE_SIZE", hdr)
        self.assertIn("64", hdr)
        sensor = (SKETCH / "sensors/pitaco_ppg_sensor.ino").read_text(encoding="utf-8")
        self.assertIn("takeFIFOReadError", sensor)

    def test_module_responsibilities_preserved(self):
        main = (SKETCH / "frimeware2.4.ino").read_text(encoding="utf-8")
        self.assertIn("PollMAX30105();", main)
        self.assertIn("PollPressureSampling();", main)
        self.assertIn("InitBleCommunication();", main)
        self.assertIn("PPG_CONTACT_MIN 5000", main)


if __name__ == "__main__":
    unittest.main()
