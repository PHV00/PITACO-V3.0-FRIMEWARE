#include <stdint.h>

// Gate 01 independente do framework: valida somente integridade basica RED/IR.
// Faixas herdadas de bancada MAX30102; recalibrar para MAX30105 real.
// PASS nao garante PPG fisiologicamente valido, BPM ou SpO2 clinicamente validos.
static const uint32_t G1_ADC_MAX = 262143UL;
static const uint32_t G1_MIN_MEAN = 5000UL;
static const uint32_t G1_MIN_RANGE = 500UL;
static const uint32_t G1_CLIP_START = G1_ADC_MAX - 2048UL;
static const uint16_t G1_MIN_SAMPLES = 50;

static uint32_t g1RedMin, g1RedMax, g1IrMin, g1IrMax;
static uint64_t g1RedSum, g1IrSum;
static uint16_t g1Samples, g1RedClips, g1IrClips;
static bool g1Gap;

void g1Reset() {
  g1RedMin = g1IrMin = G1_ADC_MAX;
  g1RedMax = g1IrMax = 0;
  g1RedSum = g1IrSum = 0;
  g1Samples = g1RedClips = g1IrClips = 0;
  g1Gap = false;
}

void g1Add(uint32_t red, uint32_t ir) {
  if (g1Samples == UINT16_MAX) { g1Gap = true; return; }
  if (red < g1RedMin) g1RedMin = red;
  if (red > g1RedMax) g1RedMax = red;
  if (ir < g1IrMin) g1IrMin = ir;
  if (ir > g1IrMax) g1IrMax = ir;
  g1RedSum += red;
  g1IrSum += ir;
  if (red >= G1_CLIP_START) ++g1RedClips;
  if (ir >= G1_CLIP_START) ++g1IrClips;
  ++g1Samples;
}
void g1MarkAcquisitionGap() { g1Gap = true; }

// reason: 0=PASS; 1=NO_SAMPLES; 2=RED_LOW; 3=IR_LOW;
// 4=RED_FLAT; 5=IR_FLAT; 6=RED_CLIP; 7=IR_CLIP;
// 8=TOO_FEW; 9=GAP.
bool g1Evaluate(uint8_t* reason, uint16_t* samples) {
  if (reason == nullptr || samples == nullptr) return false;
  *samples = g1Samples;
  *reason = 1;
  if (g1Samples == 0) return false;
  const uint32_t redMean = (uint32_t)(g1RedSum / g1Samples);
  const uint32_t irMean  = (uint32_t)(g1IrSum / g1Samples);
  if (g1Gap) *reason = 9;
  else if (g1Samples < G1_MIN_SAMPLES) *reason = 8;
  else if (redMean < G1_MIN_MEAN) *reason = 2;
  else if (irMean < G1_MIN_MEAN) *reason = 3;
  else if (g1RedMax - g1RedMin < G1_MIN_RANGE) *reason = 4;
  else if (g1IrMax - g1IrMin < G1_MIN_RANGE) *reason = 5;
  else if (g1RedClips > 0) *reason = 6;
  else if (g1IrClips > 0) *reason = 7;
  else *reason = 0;
  return *reason == 0;
}
