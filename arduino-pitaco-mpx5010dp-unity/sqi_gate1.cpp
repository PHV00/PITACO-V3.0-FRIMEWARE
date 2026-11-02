#include "sqi_gate1.h"

// Thresholds empiricos herdados de ensaios com MAX30102. Recalibrar para
// MAX30105 no dedo e na montagem optica final.
static const uint32_t ADC_MAX = 262143UL;
static const uint32_t MIN_MEAN = 5000UL;
static const uint32_t MIN_RANGE = 500UL;
static const uint32_t CLIP_START = ADC_MAX - 2048UL;
static const uint16_t MIN_WINDOW_SAMPLES = 50;

static uint32_t red_min, red_max, ir_min, ir_max;
static uint64_t red_sum, ir_sum;
static uint16_t samples, red_clipped, ir_clipped;
static bool acquisition_gap;

void g1Reset() {
  red_min = ir_min = ADC_MAX;
  red_max = ir_max = 0;
  red_sum = ir_sum = 0;
  samples = red_clipped = ir_clipped = 0;
  acquisition_gap = false;
}
void g1Add(uint32_t red, uint32_t ir) {
  if (samples == UINT16_MAX) { acquisition_gap = true; return; }
  if (red < red_min) red_min = red;
  if (red > red_max) red_max = red;
  if (ir < ir_min) ir_min = ir;
  if (ir > ir_max) ir_max = ir;
  red_sum += red;
  ir_sum += ir;
  if (red >= CLIP_START) ++red_clipped;
  if (ir >= CLIP_START) ++ir_clipped;
  ++samples;
}
void g1MarkAcquisitionGap() { acquisition_gap = true; }

G1Result g1Evaluate() {
  G1Result r = {};
  r.samples = samples;
  if (samples == 0) { r.reason = G1_NO_SAMPLES; return r; }
  r.mean_red = (uint32_t)(red_sum / samples);
  r.mean_ir = (uint32_t)(ir_sum / samples);
  r.range_red = red_max - red_min;
  r.range_ir = ir_max - ir_min;
  if (acquisition_gap) r.reason = G1_ACQUISITION_GAP;
  else if (samples < MIN_WINDOW_SAMPLES) r.reason = G1_TOO_FEW_SAMPLES;
  else if (r.mean_red < MIN_MEAN) r.reason = G1_RED_LOW_SIGNAL;
  else if (r.mean_ir < MIN_MEAN) r.reason = G1_IR_LOW_SIGNAL;
  else if (r.range_red < MIN_RANGE) r.reason = G1_RED_FLATLINE;
  else if (r.range_ir < MIN_RANGE) r.reason = G1_IR_FLATLINE;
  else if (red_clipped) r.reason = G1_RED_CLIPPING;
  else if (ir_clipped) r.reason = G1_IR_CLIPPING;
  else { r.reason = G1_OK; r.passed = true; }
  return r;
}
