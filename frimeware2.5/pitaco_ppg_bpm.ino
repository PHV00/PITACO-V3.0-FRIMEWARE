// SoC: batimentos SparkFun e calculo BPM do ESP32.
// As condicoes e coeficientes permanecem identicos ao firmware anterior.

void ProcessPpgBeat(uint32_t ir, unsigned long receiveMs, bool opticalPresent) {
    // checkForBeat(IR) da SparkFun: BPM e estimativa experimental.
    // Nunca fornecer BPM como valido antes de G1 PASS.
    // SparkFun heartRate.cpp utiliza uint16_t e int16_t internamente.
    // Normalizar 18-bit -> 15-bit apenas para BPM: RAW permanece 18-bit.
    if (ppgContactPresent && opticalPresent && checkForBeat((int32_t)(ir >> 3))) {
      ++ppgBeatDetections;
      if (lastBeatMs > 0) {
        const unsigned long delta = receiveMs - lastBeatMs;
        if (delta >= 300 && delta <= 1714) {  // 35 a 200 BPM
          const float candidate = 60000.0f / (float)delta;
          heartBpm = heartBpm > 0 ? (0.7f * heartBpm + 0.3f * candidate)
                                 : candidate;
        } else {
          heartBpm = 0.0f;
        }
      }
      lastBeatMs = receiveMs;
    }
}

bool IsPpgBpmValid(unsigned long receiveMs, bool instantContact) {
  return g1Ready && g1Passed && instantContact && heartBpm > 0
      && lastBeatMs > 0
      && (unsigned long)(receiveMs - lastBeatMs) <= 2000UL;
}
