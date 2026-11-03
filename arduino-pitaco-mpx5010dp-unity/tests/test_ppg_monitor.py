"""Testes host do modelo de middleware: sem Tk, BLE, serial ou Arduino."""
import ast
import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pitaco24_monitor import PpgMonitor
from pitaco24_protocol import parse_pitaco_line


def sample(seq=1, t_ms=1000, red=105000, ir=117000,
           contact=True, g1=True, bpm=65.1):
    return {
        "type": "sample", "seq": seq, "t_ms": t_ms,
        "ppg": {"red": red, "ir": ir,
                "bpm": bpm, "bpm_valid": bpm is not None},
        "sqi": {"g1": g1, "reason": 0 if g1 else 10, "contact": contact},
        "mpx5010dp": {"pressure_pa": 24.3, "valid": True}
    }


class PpgMonitorTests(unittest.TestCase):
    def test_sequence_loss_is_visible_not_invented(self):
        m = PpgMonitor(max_points=10)
        m.observe(sample(10, 1000), "BLE", now=100.00)
        m.observe(sample(11, 1040), "BLE", now=100.04)
        m.observe(sample(14, 1160), "BLE", now=100.16)
        s = m.snapshot(now=100.16)
        self.assertEqual(s["samples"], 3)
        self.assertEqual(s["missing"], 2)
        self.assertEqual(s["duplicates"], 0)
        self.assertEqual(s["source"], "BLE")
        self.assertEqual(len(s["history"]), 4)
        self.assertEqual(s["history"][2][1:], (None, None))
        self.assertGreater(s["sample_rate"], 0)

    def test_wrap_duplicate_and_restart(self):
        m = PpgMonitor()
        for idx, seq in enumerate([65534, 65535, 0, 0, 1]):
            m.observe(sample(seq, 1000 + idx * 40), "USB", now=100 + idx * .04)
        self.assertEqual(m.snapshot()["missing"], 0)
        self.assertEqual(m.snapshot()["duplicates"], 1)
        m.observe(sample(12, 2000), "USB", now=101)
        self.assertEqual(m.snapshot()["missing"], 10)
        m.observe(sample(1, 40), "USB", now=102)
        self.assertEqual(m.snapshot()["seq_resets"], 1)

    def test_contact_absent_and_gate_window(self):
        m = PpgMonitor()
        m.observe(sample(1, contact=False, g1=False, bpm=None,
                         red=1600, ir=2400), "USB", now=100)
        m.observe({"type": "g1", "window": 3, "t_ms": 5010,
                   "sqi": {"g1": False, "reason": 2, "samples": 125}},
                  "USB", now=101)
        s = m.snapshot()
        self.assertEqual(s["contact"], False)
        self.assertEqual(s["g1_effective"], False)
        self.assertEqual(s["bpm"], None)
        self.assertEqual(s["g1_failures"], 1)
        self.assertEqual(s["g1_reason"], 2)
        self.assertEqual(s["history"][-1][1:], (1600, 2400))

    def test_legacy_pressure_and_ble_fragments(self):
        m = PpgMonitor()
        msg = parse_pitaco_line("-21.2")
        m.observe(msg, "BLE")
        m.note_ble_fragment()
        m.note_ble_fragment()
        m.note_invalid_json()
        s = m.snapshot()
        self.assertEqual(s["pressure_messages"], 1)
        self.assertEqual(s["ble_fragments"], 2)
        self.assertEqual(s["invalid_json"], 1)
        self.assertEqual(s["samples"], 0)

    def test_csv_recording_preserves_bad_contact_and_g1(self):
        m = PpgMonitor()
        with tempfile.TemporaryDirectory() as d:
            target = pathlib.Path(d) / "bridge.csv"
            m.csv.start(target)
            m.observe(sample(1, contact=False, g1=False, bpm=None,
                             red=1423, ir=2511), "BLE")
            m.observe({"type": "g1", "window": 1, "t_ms": 5000,
                       "sqi": {"g1": False, "reason": 2, "samples": 125}},
                      "BLE")
            m.observe(parse_pitaco_line("18.5"), "BLE")
            m.csv.stop()
            with target.open(newline="", encoding="utf-8") as f:
                records = list(csv.DictReader(f))
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]["red"], "1423")
            self.assertEqual(records[0]["contact"], "False")
            self.assertEqual(records[1]["reason"], "2")
            self.assertEqual(records[2]["pressure_pa"], "18.5")
            self.assertEqual(m.snapshot()["csv_dropped"], 0)

    def test_bpm_history_rejects_bad_gate_and_contact(self):
        m = PpgMonitor()
        m.observe(sample(1, 1000, bpm=72.0), "BLE", now=100.0)
        self.assertEqual(m.snapshot()["bpm"], 72.0)
        m.observe(sample(2, 1040, contact=False, g1=False, bpm=88.0),
                  "BLE", now=100.04)
        snap = m.snapshot()
        self.assertIsNone(snap["bpm"])
        self.assertEqual(snap["bpm_history"], [(1.0, 72.0), (1.04, None)])
        self.assertEqual(snap["samples"], 2)

    def test_bpm_history_reset_does_not_keep_previous_session(self):
        m = PpgMonitor()
        m.observe(sample(1, 1000, bpm=65.1), "USB")
        self.assertEqual(len(m.snapshot()["bpm_history"]), 1)
        m.reset()
        snap = m.snapshot()
        self.assertEqual(snap["samples"], 0)
        self.assertEqual(snap["bpm_history"], [])

    def test_gui_wires_both_streams_without_touching_firmware(self):
        gui = (pathlib.Path(__file__).resolve().parents[1] /
               "ble_client_mpx5010dp.py").read_text(encoding="utf-8")
        ast.parse(gui, filename="ble_client_mpx5010dp.py")
        for token in (
            "ppg_monitor.observe(msg, source=source)",
            'source="BLE"', 'source="USB"',
            "ppg_monitor.note_ble_fragment()",
            "ppg_monitor.note_invalid_json()",
            "line_red.set_data(xs, red_values)",
            "line_ir.set_data(xs, ir_values)",
            "line_bpm.set_data(",
            'text="Gráfico Pneumo"',
            'text="Monitor Cardíaco / SpO₂"',
            "ppg_window = ctk.CTkToplevel(root)",
            "ppg_fig = Figure(figsize=(8, 6.3), dpi=100)",
            "ax_bpm = ppg_fig.add_subplot(ppg_grid[1], sharex=ax_ppg)",
            "ani_ppg = animation.FuncAnimation",
            "SpO₂: não calculada",
            "toggle_ppg_experiment()",
            "ppg_monitor.set_experimental_enabled(",
            "Calcular BPM e SpO₂ experimentais NO PYTHON",
            "line_bpm_exp.set_data(",
            "line_spo2_exp.set_data(",
            "NÃO CALIBRADA / NÃO VALIDADA",
            "if not is_ppg_plotting:",
            "if not was_active and not is_sampling:",
            "if not is_plotting:",
            "ppg_monitor.csv.start(target)",
            "ppg_monitor.csv.stop()",
            "oxi_sampling and ser_oxi",
            "PPG_NOTIFY_UUID",
            "CHARACTERISTIC_UUID"
        ):
            self.assertIn(token, gui)


if __name__ == "__main__":
    unittest.main()
