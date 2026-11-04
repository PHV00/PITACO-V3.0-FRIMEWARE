"""Testes reproduziveis offline: nao estabelecem desempenho clinico."""
import csv
import math
import pathlib
import random
import sys
import tempfile
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from pitaco_bridge.ppg_validation_25hz import (
    analyze_capture, read_capture, read_labels, sparkfun_fir_gain, threshold_sweep
)


def sample(i, red, ir, g1=True, contact=True):
    return {"type":"sample","t_ms":1000+40*i,"seq":i+1,
            "red":int(red),"ir":int(ir),"g1":g1,
            "contact":contact,"bpm_valid":False}


def window_event(n, reason=0):
    return {"type":"g1","samples":n,"reason":reason,
            "g1":reason==0,"t_ms":1000+40*n}


class Ppg25HzValidationTests(unittest.TestCase):
    def test_sweep_is_not_automatic_threshold_selection(self):
        windows = [
            {"window":1,"complete":True,"red_range":950,"ir_range":800},
            {"window":2,"complete":True,"red_range":420,"ir_range":380},
            {"window":3,"complete":False,"red_range":5000,"ir_range":5000},
        ]
        scores = threshold_sweep(windows,(300,400,500),{1:True,2:False})
        self.assertEqual([s["range_pass_windows"] for s in scores],[2,1,1])
        self.assertEqual(scores[1]["reference"]["tp"],1)
        self.assertEqual(scores[1]["reference"]["tn"],1)
        self.assertEqual(scores[0]["reference"]["fp"],1)
        self.assertEqual(scores[0]["reference"]["specificity"],0.0)

    def test_drift_is_not_equivalent_to_pulsatility(self):
        # Deriva de 1250 contagens pode aprovar o range mesmo sem onda clara.
        rows=[]
        for i in range(125):
            x=math.sin(2*math.pi*75*(i/25)/60)
            rows.append(sample(i,100000+10*i+60*x,110000+11*i+80*x))
        rows.append(window_event(125))
        result=analyze_capture(rows)
        w=result["windows"][0]
        self.assertTrue(w["complete"])
        self.assertGreater(w["red_range"],500)
        self.assertGreater(w["red_linear_trend"],900)
        self.assertLess(w["red_ac_rms"],200)
        self.assertEqual(result["summary"]["g1_windows"],1)

    def test_contact_reset_excludes_samples_before_contact(self):
        rows=[sample(0,0,0,contact=False),
              sample(1,100000,110000),sample(2,100100,110100),
              window_event(2)]
        result=analyze_capture(rows)
        self.assertEqual(result["windows"][0]["captured_samples"],2)
        self.assertTrue(result["windows"][0]["complete"])

    def test_incomplete_window_excluded_from_sweep(self):
        result=analyze_capture([sample(0,100000,110000),window_event(5)])
        self.assertFalse(result["windows"][0]["complete"])
        self.assertEqual(result["threshold_sweep"][0]["eligible_windows"],0)

    def test_missing_seq_or_timestamp_gap_is_not_called_complete(self):
        rows=[sample(i,100000+i*400,110000+i*400) for i in range(3)]
        rows[2]["seq"]=5
        result=analyze_capture(rows+[window_event(3)])
        self.assertFalse(result["windows"][0]["seq_contiguous"])
        self.assertFalse(result["windows"][0]["complete"])
        self.assertEqual(result["threshold_sweep"][0]["eligible_windows"],0)

        rows=[sample(i,100000+i*400,110000+i*400) for i in range(3)]
        rows[2]["t_ms"]+=150
        result=analyze_capture(rows+[window_event(3)])
        self.assertFalse(result["windows"][0]["timing_ok"])
        self.assertFalse(result["windows"][0]["complete"])

    def test_8s_experimental_bpm_is_opt_in_research_only(self):
        rng=random.Random(102)
        rows=[]
        for i in range(250):
            x=math.sin(2*math.pi*75*i/(25*60))
            rows.append(sample(i,100000+600*x+rng.gauss(0,10),
                               110000+1000*x+rng.gauss(0,10)))
        result=analyze_capture(rows)
        self.assertEqual(result["summary"]["firmware_bpm_valid_samples"],0)
        self.assertGreater(result["summary"]["experimental_8s_windows"],0)
        self.assertGreater(result["summary"]["experimental_bpm_available"],0)

    def test_fir_response_depends_on_rate(self):
        self.assertLess(sparkfun_fir_gain(25,120),sparkfun_fir_gain(25,60))
        self.assertLess(sparkfun_fir_gain(25,120),sparkfun_fir_gain(100,120))
        with self.assertRaises(ValueError):
            sparkfun_fir_gain(0,75)

    def test_csv_probe_and_reference_labels(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path=pathlib.Path(d)/"probe.csv"
            with csv_path.open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=[
                    "type","seq","t_ms","red","ir","bpm_valid",
                    "g1","reason","samples","contact"])
                writer.writeheader()
                writer.writerow({"type":"sample","seq":1,"t_ms":1000,
                                 "red":101000,"ir":111000,"contact":"True",
                                 "g1":"True","bpm_valid":"False"})
                writer.writerow({"type":"g1","t_ms":1040,"g1":"True",
                                 "reason":0,"samples":1})
            rows=read_capture(csv_path)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]["red"],101000)
            label_path=pathlib.Path(d)/"labels.csv"
            label_path.write_text("window,usable\n1,1\n2,0\n",encoding="utf-8")
            self.assertEqual(read_labels(label_path),{1:True,2:False})
            with self.assertRaises(ValueError):
                label_path.write_text("window,usable\n1,maybe\n",encoding="utf-8")
                read_labels(label_path)


if __name__=="__main__":
    unittest.main()
