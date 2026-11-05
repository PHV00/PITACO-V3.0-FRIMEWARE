"""Testa replay comparativo de heartRate.cpp com sinais deterministicos."""
import math
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1] / "arduino-pitaco-mpx5010dp-ble"))
from pitaco_bridge.sparkfun_pba_replay import SparkFunPbaReplay, replay_sparkfun


def synthetic(fs, bpm, seconds=30, ac=1000):
    return [{"red":100000,"ir":int(110000+ac*math.sin(2*math.pi*bpm*i/(fs*60))),
             "t_ms":round(i*1000/fs),"contact":True}
            for i in range(fs*seconds)]


class SparkFunReplayTests(unittest.TestCase):
    def test_75_bpm_detectable_at_25hz(self):
        data=replay_sparkfun(synthetic(25,75))
        self.assertGreater(data["beats_detected"],20)
        self.assertGreater(data["bpm_eligible_rr_pairs"],20)

    def test_120_bpm_attenuation_is_sampling_dependent(self):
        a=replay_sparkfun(synthetic(25,120))
        b=replay_sparkfun(synthetic(100,120))
        self.assertEqual(a["beats_detected"],0)
        self.assertGreater(b["beats_detected"],40)
        self.assertGreater(b["bpm_eligible_rr_pairs"],35)

    def test_no_contact_does_not_generate_beats(self):
        rows=synthetic(25,75,seconds=10)
        for row in rows:
            row["contact"]=False
        self.assertEqual(replay_sparkfun(rows)["beats_detected"],0)

    def test_class_and_replay_match(self):
        rows=synthetic(25,60,seconds=10)
        detector=SparkFunPbaReplay()
        beats=sum(detector.observe(row["ir"]) for row in rows)
        self.assertEqual(beats,replay_sparkfun(rows)["beats_detected"])


if __name__=="__main__":
    unittest.main()
