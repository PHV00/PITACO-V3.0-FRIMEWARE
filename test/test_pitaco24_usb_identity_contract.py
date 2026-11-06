"""Contrato do handshake direto pela USB, sem regressao de comandos."""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKETCH = ROOT / "frimeware2.4" / "frimeware2.4.ino"
COMMANDS = ROOT / "frimeware2.4" / "communication" / "pitaco_commands.ino"


class UsbIdentityContractTests(unittest.TestCase):
    def test_new_identity_is_usb_only(self):
        src = SKETCH.read_text(encoding="utf-8")
        self.assertIn("if (c == 'i')", src)
        self.assertIn('Serial.print("echo2.4p\\n");', src)
        self.assertIn("} else {", src)
        self.assertLess(src.index("if (c == 'i')"),
                        src.index("ListenCommand(c);"))

    def test_legacy_e_and_sampling_commands_preserved(self):
        src = SKETCH.read_text(encoding="utf-8")
        self.assertIn("if (c == 'e' || c == 'E')", src)
        self.assertIn('Serial.print("echop\\n");', src)
        commands = COMMANDS.read_text(encoding="utf-8")
        for fragment in ("cmd == 'e'", "cmd == 'r'", "cmd == 'f'",
                         "cmd == 'c'", "cmd == 'z'"):
            self.assertIn(fragment, commands)
        self.assertNotIn("echo2.4p", commands)

    def test_json_and_ble_modules_remain_isolated(self):
        src = SKETCH.read_text(encoding="utf-8")
        self.assertIn('#include "communication/pitaco_ble_ota.ino"', src)
        self.assertIn('#include "communication/pitaco_ppg_json.ino"', src)
        self.assertIn('#include "sensors/pitaco_respiration.ino"', src)


if __name__ == "__main__":
    unittest.main()
