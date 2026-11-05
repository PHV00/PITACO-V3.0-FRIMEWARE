"""Contratos estruturais do firmware SoC com abas .ino.

Esses testes nao substituem a compilacao ESP32-C3 nem o ensaio com sensor.
Checam invariantes do comportamento legado apos a separacao por arquivos.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / "firmware" / "pitaco_2_4"
MAIN = (ROOT / "pitaco_2_4.ino").read_text(encoding="utf-8")
SENSOR = (ROOT / "pitaco_ppg_sensor.ino").read_text(encoding="utf-8")
CONTACT = (ROOT / "pitaco_ppg_contact_sqi.ino").read_text(encoding="utf-8")
BPM = (ROOT / "pitaco_ppg_bpm.ino").read_text(encoding="utf-8")
JSON = (ROOT / "pitaco_ppg_json.ino").read_text(encoding="utf-8")
TRANSPORT = (ROOT / "pitaco_ble_ota.ino").read_text(encoding="utf-8")
COMMANDS = (ROOT / "pitaco_commands.ino").read_text(encoding="utf-8")
RESPIRATION = (ROOT / "pitaco_respiration.ino").read_text(encoding="utf-8")
G1 = (ROOT / "gate_01_integrity.ino").read_text(encoding="utf-8")


def body(source, name, return_type="void"):
    start = source.index(return_type + " " + name + "(")
    # Todas as funcoes ficam no escopo global; suas chaves finais nao
    # possuem indentacao. Os conteudos internos podem ter blocos aninhados.
    end = source.index("\n}", start) + 2
    return source[start:end]


class SocFirmwareContract(unittest.TestCase):
    def test_main_is_only_orchestration_and_shared_state(self):
        self.assertLessEqual(len(MAIN.splitlines()), 230)
        self.assertIn("void setup() {", MAIN)
        self.assertIn("void loop() {", MAIN)
        self.assertIn("InitBleCommunication();", MAIN)
        self.assertIn("InitMAX30105();", MAIN)
        self.assertIn("PollMAX30105();", MAIN)
        self.assertIn("PollPressureSampling();", MAIN)
        for forbidden in ("max30105.check()", "checkForBeat((int32_t)",
                          "analogReadMilliVolts(", "class MyServerCallbacks",
                          "BLEService* pService = "):
            self.assertNotIn(forbidden, MAIN)

    def test_single_setup_loop_and_prototype_contract(self):
        files = [MAIN, SENSOR, CONTACT, BPM, JSON, TRANSPORT,
                 COMMANDS, RESPIRATION, G1]
        combined = "\n".join(files)
        self.assertEqual(len(re.findall(r"\bvoid\s+setup\s*\(\s*\)\s*\{", combined)), 1)
        self.assertEqual(len(re.findall(r"\bvoid\s+loop\s*\(\s*\)\s*\{", combined)), 1)
        for name in ("InitBleCommunication", "PollPressureSampling",
                     "UpdatePpgContact", "ProcessPpgBeat", "IsPpgBpmValid",
                     "PublishPpgSample", "PollPpgGateWindow"):
            self.assertIn(name + "(", MAIN)
            self.assertIn(name + "(", combined)
        self.assertLess(MAIN.index("InitBleCommunication();", MAIN.index("void setup()")),
                        MAIN.index("InitMAX30105();", MAIN.index("void setup()")))
        loop = body(MAIN, "loop")
        self.assertLess(loop.index("PollMAX30105();"),
                        loop.index("PollPressureSampling();"))
        self.assertLess(loop.index("PollTenSecondZero();"),
                        loop.index("PollPressureSampling();"))

    def test_boot_ends_stopped(self):
        f = body(SENSOR, "InitMAX30105")
        self.assertLess(f.index("max30105.setup("), f.index("max30105.shutDown();"))
        self.assertIn('Serial.println("X,PPG_STATE,STOPPED")', f)

    def test_start_requires_calibration_and_prepares_fifo_before_wakeup(self):
        f = body(SENSOR, "PollMAX30105")
        for token in ("isSampling && isCalibrated",
                      "!isOtaUpdating && !zeroInProgress"):
            self.assertIn(token, f)
        start = f.index("if (!ppgSampling) {")
        start_body = f[start:f.index("} else if (", start)]
        self.assertLess(start_body.index("max30105.clearFIFO();"),
                        start_body.index("max30105.wakeUp();"))
        self.assertLess(start_body.index("max30105.wakeUp();"),
                        start_body.index("ppgSampling = true;"))
        for token in ("X,PPG_DRIVER", "X,PPG_PRESTART",
                      "PRESTART_RESET_FAILED", "WAKEUP_FAILED"):
            self.assertIn(token, start_body)

    def test_stop_suspends_conversions(self):
        f = body(SENSOR, "PollMAX30105")
        stop = f[f.index("if (!enabled) {"):f.index("const unsigned long now")]
        self.assertIn("max30105.shutDown();", stop)
        self.assertIn("return;", stop)

    def test_overflow_is_invalidated_and_recovered_after_drain(self):
        f = body(SENSOR, "PollMAX30105")
        self.assertLess(f.index("g1MarkAcquisitionGap();", f.index("const uint8_t ovf")),
                        f.index("max30105.clearFIFO();", f.index("const uint8_t ovf")))
        self.assertLess(f.index("while (max30105.available())"),
                        f.index('Serial.println("X,PPG_FIFO_RECOVERED")'))
        self.assertIn("X,PPG_SW_RING_OVERRUN", f)
        self.assertIn("const bool fifoReadError = max30105.takeFIFOReadError();", f)
        self.assertIn("X,PPG_I2C_FIFO_READ_ERROR", f)
        reset = f[f.index("if (ovf > 0 || fifoReadError) {",
                          f.index("while (max30105.available())")):]
        self.assertLess(reset.index("max30105.shutDown();"),
                        reset.index("max30105.clearFIFO();"))
        self.assertLess(reset.index("max30105.clearFIFO();"),
                        reset.index("max30105.wakeUp();"))
        self.assertIn("X,PPG_FIFO_RESET_CHECK", reset)
        self.assertIn("X,PPG_ERROR,FIFO_RESET_FAILED", reset)
        self.assertLess(reset.index('Serial.println("X,PPG_FIFO_RECOVERED")'),
                        reset.index("#if PPG_DIAG"))

    def test_live_contact_invalidates_stale_g1(self):
        update = body(CONTACT, "UpdatePpgContact", "bool")
        for token in ("PPG_CONTACT_CONFIRM_SAMPLES", "PPG_CONTACT,PRESENT",
                      "PPG_CONTACT,ABSENT", "ppgWindowStartMs = receiveMs",
                      "g1Reset();", "heartBpm = 0.0f"):
            self.assertIn(token, update if token != "PPG_CONTACT_CONFIRM_SAMPLES" else MAIN+update)
        self.assertEqual(update.count("const bool opticalPresent"), 1)
        gate = body(CONTACT, "PollPpgGateWindow")
        self.assertIn("g1Evaluate(&reason, &samples)", gate)
        self.assertIn("if (!ppgContactPresent) {", gate)
        self.assertIn("if (reason == 0) reason = 10;", gate)
        self.assertIn("SendG1Json(reason, samples);", gate)

    def test_g1_raw_bpm_and_json_preserved(self):
        f = body(SENSOR, "PollMAX30105")
        for token in ("g1Add(red, ir);", "getFIFORed()", "getFIFOIR()",
                      "ProcessPpgBeat(ir, receiveMs, opticalPresent);",
                      "PublishPpgSample(red, ir, receiveMs, opticalPresent);",
                      "PollPpgGateWindow();", "max30105.nextSample()",
                      "beats=%u,contact=%u"):
            self.assertIn(token, f)
        self.assertLess(f.index("UpdatePpgContact(red, ir, receiveMs)"),
                        f.index("g1Add(red, ir);"))
        self.assertLess(f.index("g1Add(red, ir);"),
                        f.index("ProcessPpgBeat(ir, receiveMs, opticalPresent);"))
        self.assertLess(f.index("ProcessPpgBeat(ir, receiveMs, opticalPresent);"),
                        f.index("PublishPpgSample(red, ir, receiveMs, opticalPresent);"))
        self.assertIn("checkForBeat((int32_t)(ir >> 3))", BPM)
        self.assertIn("60000.0f / (float)delta", BPM)
        self.assertIn("0.7f * heartBpm + 0.3f * candidate", BPM)
        self.assertIn("g1Ready && g1Passed", BPM)
        self.assertIn("bpmValid ? \"true\" : \"false\"", JSON)
        self.assertIn("const char* effectiveG1", JSON)
        self.assertIn("const uint8_t effectiveReason", JSON)
        self.assertIn("SendPpgJson(line);", JSON)
        self.assertIn("g1Add(uint32_t red, uint32_t ir)", G1)
        self.assertIn("G1_MIN_RANGE = 500UL", G1)

    def test_ble_ota_and_pressure_legacy_preserved(self):
        for token in ("class MyServerCallbacks", "class MyCallbacks",
                      "class OtaControlCallbacks", "class OtaDataCallbacks",
                      "Update.begin(fileSize)", "Update.write(",
                      "BLE_JSON_CHUNK_BYTES", "pPpgCharacteristic->notify()"):
            self.assertIn(token, TRANSPORT)
        for token in ("cmd == 'e'", "cmd == 'r'", "cmd == 'f'",
                      "cmd == 'c'", "cmd == 'z'", "echop"):
            self.assertIn(token, COMMANDS)
        for token in ("notifyInterval", "ReadRawPressurePa()",
                      "calibrationOffsetPa", "deadbandThreshold",
                      "pCharacteristic->notify()", "Serial.print(buf)"):
            self.assertIn(token, RESPIRATION+MAIN)
        self.assertIn("if (zeroInProgress) {", body(MAIN, "loop"))
        self.assertIn("delay(20);", RESPIRATION)
        self.assertIn("ZERO_WINDOW_MS", RESPIRATION+MAIN)


if __name__ == "__main__":
    unittest.main()
