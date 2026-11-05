"""Testes host do modelo de middleware: sem Tk, BLE, serial ou Arduino."""
import ast
import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "arduino-pitaco-mpx5010dp-ble"))

from pitaco_bridge.monitor import PpgMonitor, _rolling_mean_by_seconds
from pitaco_bridge.protocol import parse_pitaco_line


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
        self.assertEqual(m.snapshot(now=100.0)["bpm"], 72.0)
        self.assertEqual(m.snapshot(now=100.0)["fw_bpm_status"],
                         "BPM firmware valido")
        m.observe(sample(2, 1040, contact=False, g1=False, bpm=88.0),
                  "BLE", now=100.04)
        snap = m.snapshot(now=100.04)
        self.assertEqual(snap["fw_bpm_status"], "Sem contato")
        self.assertIsNone(snap["bpm"])
        self.assertEqual(snap["bpm_history"], [(1.0, 72.0), (1.04, None)])
        self.assertEqual(snap["samples"], 2)

    def test_bpm_missing_reason_and_stale_timeout(self):
        m = PpgMonitor()
        m.observe(sample(1, 1000, bpm=None), "BLE", now=100.00)
        good = m.snapshot(now=100.05)
        self.assertIsNone(good["bpm"])
        self.assertEqual(good["fw_bpm_status"],
                         "Firmware ainda sem BPM valido")
        m.observe(sample(2, 1040, bpm=72.0), "BLE", now=100.04)
        self.assertEqual(m.snapshot(now=100.08)["bpm"], 72.0)
        expired = m.snapshot(now=102.10)
        self.assertIsNone(expired["bpm"])
        self.assertEqual(expired["fw_bpm_status"], "Sem amostras recentes")
        self.assertEqual(expired["bpm_history"][-1], (1.04, 72.0))

    def test_bpm_history_reset_does_not_keep_previous_session(self):
        m = PpgMonitor()
        m.observe(sample(1, 1000, bpm=65.1), "USB")
        self.assertEqual(len(m.snapshot()["bpm_history"]), 1)
        m.reset()
        snap = m.snapshot()
        self.assertEqual(snap["samples"], 0)
        self.assertEqual(snap["bpm_history"], [])


    def test_60s_averages_each_second_equally_instead_of_each_sample(self):
        # A taxa de mensagens nao deve enviesar a media do minuto.
        many_in_first_second = [(0.04*i, 60.0) for i in range(20)]
        values = many_in_first_second + [(1.0, 70.0), (2.0, 80.0)]
        result = _rolling_mean_by_seconds(values, latest_s=2.0,
                                          segment_start_s=0.0)
        self.assertEqual(result["value"], 70.0)
        self.assertEqual(result["valid_seconds"], 3)
        self.assertEqual(result["status"], "parcial")

    def test_bpm_and_spo2_rolling_mean_full_60s_independent_of_raw_chart(self):
        m = PpgMonitor(max_points=15)
        with m._lock:
            m.mean_segment_start_s = 0.0
            m.contact = True
            m.last_t_ms = 65000
            m.last_rx = 100.0
            for sec in range(66):
                m.bpm_mean_history.append((float(sec), 70.0))
                m.experimental.bpm_history.append((float(sec), 80.0))
                m.experimental.spo2_history.append((float(sec), 96.0))
            # Apenas 15 pontos na tela; media 60s deve continuar correta.
            self.assertEqual(m.history.maxlen, 15)
        snap = m.snapshot(now=100.0)
        for name, expected in (("bpm_fw", 70.0), ("bpm_py", 80.0),
                               ("spo2", 96.0)):
            metric = snap["mean60"][name]
            self.assertEqual(metric["value"], expected)
            self.assertEqual(metric["status"], "completa")
            self.assertEqual(metric["valid_seconds"], 60)

        # Ao perder telemetria, o ultimo minuto nao vira leitura atual.
        stale = m.snapshot(now=102.2)
        self.assertTrue(all(x["value"] is None
                            for x in stale["mean60"].values()))
        self.assertTrue(all(x["status"] == "indisponivel"
                            for x in stale["mean60"].values()))

    def test_60s_mean_is_partial_until_one_minute_and_excludes_none(self):
        data = [(float(sec), 90.0 if sec % 2 == 0 else None)
                for sec in range(21)]
        metric = _rolling_mean_by_seconds(data, 20.0, 0.0)
        self.assertEqual(metric["value"], 90.0)
        self.assertEqual(metric["valid_seconds"], 11)
        self.assertEqual(metric["status"], "parcial")
        self.assertIsNone(_rolling_mean_by_seconds(
            [(0.0, 60), (1.0, 70)], 1.0, 0.0)["value"])

    def test_no_contact_and_reposition_reset_mean_without_erasing_history(self):
        m = PpgMonitor()
        for i, sec in enumerate((1, 2, 3), start=1):
            m.observe(sample(i, sec*1000, bpm=70.0), "USB",
                      now=100.0 + sec)
        before = m.snapshot(now=103.0)
        self.assertEqual(before["mean60"]["bpm_fw"]["value"], 70.0)
        previous_history_length = len(before["bpm_history"])

        m.observe(sample(4, 4000, contact=False, g1=False, bpm=None,
                         red=1200, ir=1000), "USB", now=104.0)
        absent = m.snapshot(now=104.0)
        self.assertIsNone(absent["mean60"]["bpm_fw"]["value"])
        self.assertIsNone(absent["mean60"]["spo2"]["value"])
        self.assertGreater(len(absent["bpm_history"]), previous_history_length)

        # Amostras da colocacao antiga nao entram na media apos retorno.
        for i, sec in enumerate((5, 6, 7), start=5):
            m.observe(sample(i, sec*1000, bpm=100.0), "USB",
                      now=100.0 + sec)
        after = m.snapshot(now=107.0)
        self.assertEqual(after["mean60"]["bpm_fw"]["value"], 100.0)
        self.assertEqual(after["mean60"]["bpm_fw"]["status"], "parcial")

    def test_gui_wires_both_streams_without_touching_firmware(self):
        gui_dir = (pathlib.Path(__file__).resolve().parents[1] / "arduino-pitaco-mpx5010dp-ble" /
                   "pitaco_bridge" / "gui")
        main_source = (gui_dir / "main_window.py").read_text(encoding="utf-8")
        pneumo_source = (gui_dir / "pneumo_view.py").read_text(encoding="utf-8")
        cardio_source = (gui_dir / "oxy_and_cardio_view.py").read_text(encoding="utf-8")
        for filename, source in (
            ("main_window.py", main_source),
            ("pneumo_view.py", pneumo_source),
            ("oxy_and_cardio_view.py", cardio_source),
        ):
            ast.parse(source, filename=filename)
        gui = main_source + pneumo_source + cardio_source
        # O oxímetro é parte do ESP32 e chega pelo JSON já recebido;
        # o middleware não deve recriar uma porta COM para ele.
        for forbidden in ("oxi_port_var", "oxi_port_combo", "ser_oxi",
                          "oxi_sampling", "oximeter_command_loop",
                          "oximeter_game_port", "last_oxi_sent"):
            self.assertNotIn(forbidden, main_source)
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
            "SpO₂ EXP.: --",
            "BPM Python EXP.: --",
            "ppg_metric_bpm = ctk.CTkFrame(",
            "ppg_metric_spo2 = ctk.CTkFrame(",
            "ppg_metric_bpm_mean = ctk.CTkFrame(",
            "ppg_metric_spo2_mean = ctk.CTkFrame(",
            "ppg_spo2_mean_value.configure(",
            "ppg_bpm_fw_mean_value.configure(",
            "ppg_spo2_value.configure(text=spo2_text)",
            "ppg_quality_label.configure(",
            "Reinícios seq:",
            "line_bpm_exp.set_data(",
            "bpm_fw_corner.set_text(",
            "bpm_py_corner.set_text(",
            "fw_bpm_status",
            "ESP32: -- BPM",
            "Python EXP.: -- BPM",
            "line_spo2_exp.set_data(",
            "NÃO CALIBRADA / NÃO VALIDADA",
            "if not is_ppg_plotting:",
            "if not was_active and not is_sampling:",
            "if not is_plotting:",
            "ppg_monitor.csv.start(target)",
            "ppg_monitor.csv.stop()",
            "PPG_NOTIFY_UUID",
            "CHARACTERISTIC_UUID"
        ):
            self.assertIn(token, gui)
        self.assertNotIn("CTkCheckBox(", cardio_source)
        self.assertNotIn("toggle_ppg_experiment", gui)
        self.assertNotIn("set_experimental_enabled", gui)


if __name__ == "__main__":
    unittest.main()
