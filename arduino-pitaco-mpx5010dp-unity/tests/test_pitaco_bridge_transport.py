"""Contrato do roteador USB/BLE isolado de Tk, Bluetooth e portas COM."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pitaco_bridge.monitor import PpgMonitor
from pitaco_bridge.transport import PitacoMessageRouter


def sample(seq, bpm=None, contact=True, g1=True, pressure=22.0):
    return dict(type="sample", seq=seq, t_ms=seq*40,
                ppg=dict(red=90000, ir=110000, bpm=bpm,
                         bpm_valid=bpm is not None),
                sqi=dict(contact=contact, g1=g1, reason=0 if g1 else 2),
                mpx5010dp=dict(pressure_pa=pressure, valid=True))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.monitor = PpgMonitor()
        self.pressures = []
        self.sent = []
        self.errors = []
        self.now = 10.0
        self.router = PitacoMessageRouter(
            monitor=self.monitor,
            on_pressure=self.pressures.append,
            can_send_bpm=lambda: True,
            send_bpm=self.sent.append,
            report_error=self.errors.append,
            clock=lambda: self.now)

    def test_plain_pressure_and_usb_sample_preserve_pneumo(self):
        self.assertTrue(self.router.process_line("25.5", source="USB"))
        self.assertTrue(self.router.process_line(
            json.dumps(sample(1, pressure=30.7)), source="USB"))
        self.assertEqual(self.pressures, [25.5, 30.7])
        self.assertEqual(self.monitor.snapshot()["samples"], 1)

    def test_ble_ppg_fragments_do_not_update_pressure(self):
        raw = json.dumps(sample(1), separators=(",", ":")).encode() + b"\n"
        self.assertEqual(self.router.feed_ble_ppg(raw[:12]), 0)
        self.assertEqual(self.monitor.snapshot()["samples"], 0)
        self.assertEqual(self.router.feed_ble_ppg(raw[12:]), 1)
        self.assertEqual(self.monitor.snapshot()["samples"], 1)
        self.assertEqual(self.pressures, [])
        self.assertEqual(self.monitor.snapshot()["ble_fragments"], 2)

    def test_bad_json_counted_without_fabricating_samples(self):
        self.router.feed_ble_ppg(b"{invalid}\n")
        snap = self.monitor.snapshot()
        self.assertEqual(snap["invalid_json"], 1)
        self.assertEqual(snap["samples"], 0)

    def test_bpm_fw_gated_rate_limited_spo2_unavailable(self):
        self.router.process_line(json.dumps(sample(1, bpm=75)), source="USB")
        self.assertEqual(self.sent, [75])
        self.router.process_line(json.dumps(sample(2, bpm=80)), source="USB")
        self.assertEqual(self.sent, [75])
        self.now += 1.01
        self.router.process_line(json.dumps(sample(3, bpm=82, g1=False)), source="USB")
        self.assertEqual(self.sent, [75])
        self.router.process_line(json.dumps(sample(4, bpm=82)), source="USB")
        self.assertEqual(self.sent, [75, 82])

    def test_new_session_resets_fragments(self):
        raw = json.dumps(sample(1)).encode() + b"\n"
        self.router.feed_ble_ppg(raw[:10])
        self.router.reset_session()
        self.router.feed_ble_ppg(raw)
        self.assertEqual(self.monitor.snapshot()["samples"], 1)


if __name__ == "__main__":
    unittest.main()
