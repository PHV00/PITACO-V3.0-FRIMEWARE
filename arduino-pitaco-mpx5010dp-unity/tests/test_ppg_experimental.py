"""Testes deterministas de BPM/SpO2 demo; nunca teste de exatidao clinica."""
import math
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pitaco_bridge.experimental import ExperimentalPpgAnalyzer, estimate_experimental
from pitaco_bridge.monitor import PpgMonitor


def synthetic(bpm=75.0, seconds=10, red_ac=600, ir_ac=1000, noise=10):
    """Senoides artificiais: R alvo=(red_ac/100000)/(ir_ac/110000)."""
    rng = random.Random(102)
    n = int(seconds * 25)
    out = []
    for i in range(n):
        t = i * 40
        pulse = math.sin(2*math.pi*bpm*(t/1000)/60)
        out.append((t, 100000 + red_ac*pulse + rng.gauss(0, noise),
                    110000 + ir_ac*pulse + rng.gauss(0, noise)))
    return out


def msg(i, t, red, ir, contact=True, g1=True):
    return {
        "type": "sample", "seq": i+1, "t_ms": t,
        "ppg": {"red": int(red), "ir": int(ir),
                "bpm": None, "bpm_valid": False},
        "sqi": {"contact": contact, "g1": g1, "reason": 0 if g1 else 2},
        "mpx5010dp": {"pressure_pa": 20.0, "valid": True}
    }


class ExperimentalPpgTests(unittest.TestCase):
    def test_synthetic_bpm_spo2_ratio(self):
        result = estimate_experimental(synthetic())
        self.assertAlmostEqual(result["bpm"], 75, delta=3)
        self.assertAlmostEqual(result["ratio"], .66, delta=.06)
        self.assertGreater(result["spo2"], 93)
        self.assertLess(result["spo2"], 98)
        self.assertEqual(result["status"], "DEMONSTRACAO NAO VALIDADA")

    def test_realtime_window_starts_before_eight_seconds(self):
        # A janela curta permite detectar ritmo com 3-4 segundos de sinal.
        analyser = ExperimentalPpgAnalyzer()
        for i, (t, red, ir) in enumerate(synthetic(bpm=110, seconds=4)):
            analyser.observe(msg(i, t, red, ir))
        snap = analyser.snapshot()
        self.assertAlmostEqual(snap["bpm"], 110, delta=5)
        self.assertIsNotNone(snap["spo2"])
        # Atualizacao progressiva, sem esperar os antigos 8 s / 1 Hz.
        self.assertGreaterEqual(len(snap["bpm_history"]), 8)

    def test_g1_pending_is_diagnostic_but_contact_remains_required(self):
        analyser = ExperimentalPpgAnalyzer()
        for i, (t, red, ir) in enumerate(synthetic(bpm=100, seconds=4)):
            analyser.observe(msg(i, t, red, ir, g1=False))
        snap = analyser.snapshot()
        self.assertAlmostEqual(snap["bpm"], 100, delta=6)
        self.assertIsNotNone(snap["spo2"])
        self.assertFalse(snap["quality"]["g1"])
        self.assertIn("G1 reprovado", snap["quality"]["warnings"])

        # Nenhum valor deve aparecer com ausencia de contato, mesmo sem G1.
        analyser.observe(msg(101, 4040, 1220, 1045, contact=False, g1=False))
        self.assertIsNone(analyser.snapshot()["bpm"])
        self.assertIsNone(analyser.snapshot()["spo2"])

    def test_short_recording_without_contact_cannot_generate_spo2(self):
        # Reproduz escala/duracao da captura de bancada enviada (28 amostras).
        analyser = ExperimentalPpgAnalyzer()
        for i in range(28):
            analyser.observe(msg(i, 1436097 + 40*i, 1220, 1045,
                                 contact=False, g1=False))
        self.assertIsNone(analyser.snapshot()["bpm"])
        self.assertIsNone(analyser.snapshot()["spo2"])

    def test_spo2_is_independent_of_bpm_periodicity(self):
        # Dois canais correlacionados e com AC/DC plausiveis, mas a sequencia
        # pseudoaleatoria nao tem periodicidade cardiaca bem definida.
        rng = random.Random(920)
        rows = []
        for i in range(250):
            pulse = rng.gauss(0, 1.0)
            rows.append((i * 40, 100000 + 600*pulse,
                         110000 + 1000*pulse))
        result = estimate_experimental(rows)
        self.assertIsNone(result["bpm"])
        self.assertIsNotNone(result["spo2"])
        self.assertAlmostEqual(result["ratio"], .66, delta=.06)
        self.assertIn("IR sem periodicidade BPM suficiente", result["warnings"])

    def test_quality_is_separate_from_g1_and_contact(self):
        good = ExperimentalPpgAnalyzer()
        bad = ExperimentalPpgAnalyzer()
        data = synthetic(seconds=10)
        for i, (t, red, ir) in enumerate(data):
            good.observe(msg(i, t, red, ir, contact=True, g1=True))
            bad.observe(msg(i, t, red, ir, contact=False, g1=False))
        g, b = good.snapshot(), bad.snapshot()
        self.assertEqual(g["bpm"], b["bpm"])
        self.assertEqual(g["spo2"], b["spo2"])
        self.assertIsNotNone(b["bpm"])
        self.assertIsNotNone(b["spo2"])
        self.assertEqual(b["quality"]["contact"], False)
        self.assertEqual(b["quality"]["g1"], False)
        self.assertIn("Contato ausente/desconhecido", b["quality"]["warnings"])
        self.assertIn("G1 reprovado", b["quality"]["warnings"])

    def test_quality_drop_preserves_previous_estimates_in_history(self):
        analyser = ExperimentalPpgAnalyzer()
        for i, (t, red, ir) in enumerate(synthetic(seconds=10)):
            analyser.observe(msg(i, t, red, ir))
        original = analyser.snapshot()
        self.assertIsNotNone(original["bpm"])
        self.assertIsNotNone(original["spo2"])
        previous_bpm = [v for _, v in original["bpm_history"] if v is not None]
        previous_spo2 = [v for _, v in original["spo2_history"] if v is not None]
        self.assertTrue(previous_bpm)
        self.assertTrue(previous_spo2)
        analyser.observe(msg(250, 10000, 1220, 1040, contact=False, g1=False))
        interrupted = analyser.snapshot()
        self.assertIsNone(interrupted["bpm"])
        self.assertIsNone(interrupted["spo2"])
        self.assertEqual([v for _, v in interrupted["bpm_history"] if v is not None],
                         previous_bpm)
        self.assertEqual([v for _, v in interrupted["spo2_history"] if v is not None],
                         previous_spo2)
        self.assertEqual(interrupted["bpm_history"][-1][1], None)
        self.assertEqual(interrupted["spo2_history"][-1][1], None)
        # Continuar sem contato nao apaga o que foi coletado.
        for i in range(251, 290):
            analyser.observe(msg(i, i*40, 1220, 1040, contact=False, g1=False))
        self.assertEqual([v for _, v in analyser.snapshot()["bpm_history"]
                          if v is not None], previous_bpm)

    def test_range_without_spo2_still_allows_bpm(self):
        data = synthetic(red_ac=1600, ir_ac=400)
        result = estimate_experimental(data)
        self.assertIsNotNone(result["bpm"])
        self.assertIsNone(result["spo2"])
        self.assertGreater(result["ratio"], 1.4)

    def test_motion_is_rejected(self):
        data = synthetic()
        t, red, ir = data[80]
        data[80] = (t, red+50000, ir+65000)
        result = estimate_experimental(data)
        # Movimento bruto agora e aviso de qualidade, nao gate global do
        # calculo diagnostico. Pode existir candidato, mas nunca e validado.
        self.assertIn("Variacao optica ampla (possivel movimento)",
                      result["warnings"])

    def test_constant_signal_is_rejected(self):
        data = [(i*40, 100000, 110000) for i in range(210)]
        result = estimate_experimental(data)
        self.assertIsNone(result["bpm"])
        self.assertIsNone(result["spo2"])

    def test_enabled_automatically_and_contact_gates(self):
        analyser = ExperimentalPpgAnalyzer()
        self.assertTrue(analyser.snapshot()["enabled"])
        self.assertEqual(analyser.snapshot()["status"], "Aguardando sinal / contato")
        for i, (t, red, ir) in enumerate(synthetic()):
            analyser.observe(msg(i,t,red,ir))
        self.assertAlmostEqual(analyser.snapshot()["bpm"], 75, delta=3)
        self.assertIsNotNone(analyser.snapshot()["spo2"])
        analyser.observe(msg(251, 10040, 1500, 1800, contact=False, g1=False))
        self.assertIsNone(analyser.snapshot()["bpm"])
        self.assertIsNone(analyser.snapshot()["spo2"])
        self.assertEqual(analyser.snapshot()["bpm_history"][-1][1], None)

    def test_gap_clears_estimate_until_new_window(self):
        analyser = ExperimentalPpgAnalyzer()
        for i, (t, red, ir) in enumerate(synthetic()):
            analyser.observe(msg(i,t,red,ir))
        self.assertIsNotNone(analyser.snapshot()["bpm"])
        analyser.observe(msg(250, 12000, 100000, 110000), gap=True)
        self.assertIsNone(analyser.snapshot()["bpm"])
        self.assertIsNone(analyser.snapshot()["spo2"])

    def test_disconnected_monitor_does_not_keep_live_estimate(self):
        m = PpgMonitor()
        for i, (t, red, ir) in enumerate(synthetic()):
            m.observe(msg(i, t, red, ir), "BLE", now=100+i*.04)
        current = m.snapshot(now=110.0)["experimental"]
        self.assertIsNotNone(current["bpm"])
        stale = m.snapshot(now=113.0)["experimental"]
        self.assertIsNone(stale["bpm"])
        self.assertIsNone(stale["spo2"])
        self.assertEqual(stale["status"], "Sem amostras recentes")
        self.assertEqual(stale["bpm_history"], current["bpm_history"])

    def test_monitor_still_keeps_all_raw_and_legacy_bpm(self):
        m = PpgMonitor(max_points=300)
        self.assertTrue(m.snapshot()["experimental"]["enabled"])
        for i, (t, red, ir) in enumerate(synthetic()):
            m.observe(msg(i,t,red,ir), "USB", now=100+i*.04)
        snap = m.snapshot(now=110)
        self.assertEqual(snap["samples"], 250)
        self.assertEqual(snap["missing"], 0)
        self.assertAlmostEqual(snap["experimental"]["bpm"], 75, delta=3)
        self.assertEqual(snap["experimental"]["status"],
                         "DEMONSTRACAO NAO VALIDADA")
        self.assertIsNone(snap["bpm"])  # firmware sem batimentos
        self.assertEqual(len(snap["history"]), 250)  # RAW permanece intacto
        m.reset()
        self.assertEqual(m.snapshot()["samples"], 0)
        self.assertEqual(m.snapshot()["experimental"]["bpm_history"], [])
        self.assertTrue(m.snapshot()["experimental"]["enabled"])


if __name__ == "__main__":
    unittest.main()
