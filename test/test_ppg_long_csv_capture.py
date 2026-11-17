"""Regressao: CSV longo preserva TODAS as amostras e eventos G1.

O relogio e simulado; nao e necessario esperar dois minutos para o teste.
O arquivo de gravacao nao depende do deque limitado do grafico.
"""
import csv
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arduino-pitaco-mpx5010dp-ble"))

from pitaco_bridge.monitor import PpgCsvRecorder, CSV_FIELDS


class TestLongCsvCapture(unittest.TestCase):

    def test_complete_120_second_stream_keeps_failed_g1_and_contact_gaps(self):
        recorder = PpgCsvRecorder(max_pending=8192)
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "pitaco24_ppg_full_test.csv"
            # Simula 25 Hz x 120s sem alterar o clock real da thread de escrita.
            with patch("pitaco_bridge.monitor.time.monotonic", return_value=1000.0):
                recorder.start(target)
            for i in range(3000):
                t_ms = i * 40
                contact = i not in (625, 626, 627)
                recorder.record({
                    "type": "sample", "seq": i, "t_ms": t_ms,
                    "ppg": {"red": 42000 + (i % 500),
                            "ir": 49000 + (i % 700),
                            "bpm": 70, "bpm_valid": True},
                    "sqi": {"g1": contact, "contact": contact,
                            "reason": 0 if contact else 10},
                }, "BLE", 1000.0 + i * 0.04)
                if (i + 1) % 125 == 0:
                    window = (i + 1) // 125
                    passed = window != 6
                    recorder.record({
                        "type": "g1", "window": window, "t_ms": t_ms,
                        "sqi": {"g1": passed,
                                "reason": 0 if passed else 4, "samples": 125},
                    }, "BLE", 1000.0 + i * 0.04)
            recorder.stop()
            with target.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(tuple(reader.fieldnames), CSV_FIELDS)
                records = list(reader)

        samples = [r for r in records if r["type"] == "sample"]
        windows = [r for r in records if r["type"] == "g1"]
        self.assertEqual(len(records), 3024)
        self.assertEqual(len(samples), 3000)
        self.assertEqual(len(windows), 24)
        self.assertEqual(samples[625]["contact"], "False")
        self.assertEqual(windows[5]["g1"], "False")
        self.assertEqual(windows[5]["reason"], "4")
        self.assertEqual(samples[0]["transport"], "BLE")
        self.assertGreaterEqual(float(samples[-1]["rx_s"]), 119.9)
        self.assertEqual(recorder.dropped, 0)
        self.assertEqual(recorder.written, 3024)
        self.assertFalse(recorder.active)

    def test_gui_has_separate_automatic_log_and_disconnect_cleanup(self):
        view = (ROOT / "arduino-pitaco-mpx5010dp-ble" /
                "pitaco_bridge" / "gui" / "oxy_and_cardio_view.py").read_text(
                    encoding="utf-8")
        main = (ROOT / "arduino-pitaco-mpx5010dp-ble" /
                "pitaco_bridge" / "gui" / "main_window.py").read_text(
                    encoding="utf-8")
        self.assertIn("Gerar log completo", view)
        self.assertIn('"2 min": 120', view)
        self.assertIn("root.after(250, update_timed_capture)", view)
        self.assertIn("stop_ppg_csv=stop_ppg_csv", view)
        self.assertIn('oxy_and_cardio_view.stop_ppg_csv("desconexao")', main)


if __name__ == "__main__":
    unittest.main()
