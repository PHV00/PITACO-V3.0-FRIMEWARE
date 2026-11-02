"""Regressao estatico-estrutural dos estados PPG; nao substitui teste com sensor."""
from pathlib import Path
import unittest

SKETCH = (Path(__file__).resolve().parents[1] /
          "arduino-pitaco-mpx5010dp-unity.ino").read_text(encoding="utf-8")


def body(name):
    start = SKETCH.index("void " + name + "() {")
    if name == "InitMAX30105":
        end = SKETCH.index("void SendPpgJson(", start)
    elif name == "PollMAX30105":
        end = len(SKETCH)
    else:
        raise ValueError(name)
    return SKETCH[start:end]


class AcquisitionLifecycleContract(unittest.TestCase):
    def test_boot_ends_stopped(self):
        f = body("InitMAX30105")
        self.assertLess(f.index("max30105.setup("), f.index("max30105.shutDown();"))
        self.assertIn('Serial.println("X,PPG_STATE,STOPPED")', f)

    def test_start_requires_calibration_and_wakes_first(self):
        f = body("PollMAX30105")
        for token in ("isSampling && isCalibrated",
                      "!isOtaUpdating && !zeroInProgress"):
            self.assertIn(token, f)
        start = f.index("if (!ppgSampling) {")
        start_body = f[start:f.index("} else if (", start)]
        self.assertLess(start_body.index("max30105.wakeUp();"),
                        start_body.index("max30105.clearFIFO();"))
        self.assertLess(start_body.index("max30105.clearFIFO();"),
                        start_body.index("ppgSampling = true;"))

    def test_stop_suspends_conversions(self):
        f = body("PollMAX30105")
        stop = f[f.index("if (!enabled) {"):f.index("const unsigned long now", 0)]
        self.assertIn("max30105.shutDown();", stop)
        self.assertIn("return;", stop)

    def test_overflow_is_invalidated_and_recovered_after_drain(self):
        f = body("PollMAX30105")
        self.assertLess(f.index("g1MarkAcquisitionGap();", f.index("const uint8_t ovf")),
                        f.index("max30105.clearFIFO();", f.index("const uint8_t ovf")))
        self.assertLess(f.index("while (max30105.available())"),
                        f.index('Serial.println("X,PPG_FIFO_RECOVERED")'))
        self.assertIn('X,PPG_SW_RING_OVERRUN', f)

    def test_g1_and_raw_values_are_preserved(self):
        f = body("PollMAX30105")
        for token in ("g1Add(red, ir);", "getFIFORed()",
                      "getFIFOIR()", "checkForBeat(", "SendPpgJson(line)",
                      "max30105.nextSample()", "g1Evaluate(&reason, &samples)"):
            self.assertIn(token, f)


if __name__ == "__main__":
    unittest.main()
