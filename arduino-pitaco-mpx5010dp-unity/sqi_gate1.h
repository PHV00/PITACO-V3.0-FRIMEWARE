#pragma once
#include <stdint.h>

// Criterios PROVISORIOS de bancada; G1 PASS nao valida SpO2 clinicamente.
enum G1Reason : uint8_t {
  G1_OK = 0, G1_NO_SAMPLES = 1,
  G1_RED_LOW_SIGNAL = 2, G1_IR_LOW_SIGNAL = 3,
  G1_RED_FLATLINE = 4, G1_IR_FLATLINE = 5,
  G1_RED_CLIPPING = 6, G1_IR_CLIPPING = 7,
  G1_TOO_FEW_SAMPLES = 8, G1_ACQUISITION_GAP = 9
};

struct G1Result {
  bool passed;
  uint8_t reason;
  uint16_t samples;
  uint32_t mean_red, mean_ir, range_red, range_ir;
};
void g1Reset();
void g1Add(uint32_t red, uint32_t ir);
void g1MarkAcquisitionGap();
G1Result g1Evaluate();
