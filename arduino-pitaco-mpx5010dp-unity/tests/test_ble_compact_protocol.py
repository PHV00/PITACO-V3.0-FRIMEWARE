"""Contrato BLE compacto v1; testes host independentes do hardware."""
import binascii
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pitaco24_protocol import decode_ble_ppg_frame, parse_pitaco_line


def frame(kind=1, seq=65535, t_ms=1234567, red=120000, ir=123456,
          bpm10=651, flags=15, reason=0, samples=125, passed=1):
    data = bytearray(20)
    data[0] = 0xA5
    data[1] = kind
    struct.pack_into("<HI", data, 2, seq, t_ms)
    if kind == 1:
        data[8:11] = red.to_bytes(3, "little")
        data[11:14] = ir.to_bytes(3, "little")
        struct.pack_into("<H", data, 14, bpm10)
        data[16], data[17] = flags, reason
    else:
        struct.pack_into("<H", data, 8, samples)
        data[10], data[11] = reason, passed
    struct.pack_into("<H", data, 18, binascii.crc_hqx(data[:18], 0xFFFF))
    return bytes(data)


class BleCompactProtocolTests(unittest.TestCase):
    def test_valid_sample_and_wrap(self):
        sample = decode_ble_ppg_frame(frame())
        self.assertEqual(sample["seq"], 65535)
        self.assertEqual(sample["ppg"]["red"], 120000)
        self.assertEqual(sample["ppg"]["ir"], 123456)
        self.assertEqual(sample["ppg"]["bpm"], 65.1)
        self.assertTrue(sample["sqi"]["contact"])
        self.assertTrue(sample["sqi"]["g1"])
        self.assertEqual(parse_pitaco_line(__import__("json").dumps(sample)), sample)

    def test_invalid_contact_still_contains_raw(self):
        sample = decode_ble_ppg_frame(frame(red=1690, ir=2288,
                                            flags=0, reason=10, bpm10=65535))
        self.assertFalse(sample["sqi"]["contact"])
        self.assertFalse(sample["sqi"]["g1"])
        self.assertFalse(sample["ppg"]["bpm_valid"])
        self.assertIsNone(sample["ppg"]["bpm"])
        self.assertEqual(sample["ppg"]["red"], 1690)

    def test_g1_not_yet_evaluated(self):
        sample = decode_ble_ppg_frame(frame(flags=2, reason=1, bpm10=65535))
        self.assertIsNone(sample["sqi"]["g1"])

    def test_valid_g1_window(self):
        result = decode_ble_ppg_frame(frame(kind=2, seq=7, samples=125,
                                             reason=2, passed=0))
        self.assertEqual(result["window"], 7)
        self.assertEqual(result["sqi"], {"g1": False, "reason": 2, "samples": 125})

    def test_bad_crc_rejected(self):
        msg = bytearray(frame())
        msg[8] ^= 1
        with self.assertRaises(ValueError):
            decode_ble_ppg_frame(msg)

    def test_bad_size_type_and_magic(self):
        for bad in (b"", frame()[:19], b"\x00" + frame()[1:]):
            with self.assertRaises(ValueError):
                decode_ble_ppg_frame(bad)
        with self.assertRaises(ValueError):
            decode_ble_ppg_frame(frame(kind=3))

    def test_invalid_adc_flag_and_bpm(self):
        for invalid in (
            frame(red=262144),
            frame(flags=0x1F),
            frame(flags=15, bpm10=65535),
            frame(flags=0, bpm10=651),
            frame(flags=8, bpm10=65535),
            frame(flags=13, bpm10=651),
        ):
            with self.subTest(invalid=invalid.hex()), self.assertRaises(ValueError):
                decode_ble_ppg_frame(invalid)

    def test_g1_reserved_bytes_rejected(self):
        msg = bytearray(frame(kind=2))
        msg[12] = 1
        struct.pack_into("<H", msg, 18, binascii.crc_hqx(msg[:18], 0xFFFF))
        with self.assertRaises(ValueError):
            decode_ble_ppg_frame(msg)

    def test_firmware_still_has_legacy_contract(self):
        sketch = (pathlib.Path(__file__).resolve().parents[1] /
                  "arduino-pitaco-mpx5010dp-unity.ino").read_text(encoding="utf8")
        for token in ('#define CHARACTERISTIC_UUID "3bcdff27',
                      '#define PPG_NOTIFY_UUID "3bcdff2a',
                      '#define PPG_BINARY_NOTIFY_UUID "3bcdff2b',
                      "pPpgJsonCccd->getNotifications()",
                      "blePpgNotify(p);",
                      "SendPpgJson(line);",
                      "sendBlePpgSample(ppgSeq",
                      "sendBlePpgG1(g1Window"):
            self.assertIn(token, sketch)


if __name__ == "__main__":
    unittest.main()
