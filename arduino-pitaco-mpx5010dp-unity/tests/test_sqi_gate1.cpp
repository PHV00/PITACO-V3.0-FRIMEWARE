#include "../sqi_gate1.h"
#include <assert.h>
#include <stdio.h>

static void finger() {
  g1Reset();
  for (unsigned i=0; i<125; ++i)
    g1Add(106000u+(i%7u)*250u, 118000u+(i%9u)*350u);
  assert(g1Evaluate().passed);
}
int main() {
  finger();
  g1Reset();
  for (unsigned i=0;i<125;++i) g1Add(600u+i%20u,550u+i%15u);
  assert(g1Evaluate().reason == G1_RED_LOW_SIGNAL);
  g1Reset();
  for (unsigned i=0;i<125;++i) g1Add(100000u,120000u+i*20u);
  assert(g1Evaluate().reason == G1_RED_FLATLINE);
  g1Reset();
  for (unsigned i=0;i<125;++i)
    g1Add(i==50?262143u:106000u+(i%5u)*200u,118000u+(i%7u)*220u);
  assert(g1Evaluate().reason == G1_RED_CLIPPING);
  g1Reset();
  for (unsigned i=0;i<10;++i) g1Add(100000u+i*120u,120000u+i*110u);
  assert(g1Evaluate().reason == G1_TOO_FEW_SAMPLES);
  g1Reset();
  for (unsigned i=0;i<125;++i)
    g1Add(106000u+(i%5u)*200u,118000u+(i%7u)*220u);
  g1MarkAcquisitionGap();
  assert(g1Evaluate().reason == G1_ACQUISITION_GAP);
  g1Reset();
  assert(g1Evaluate().reason == G1_NO_SAMPLES);
  puts("PASS: 7 scenarios SQI G1");
  return 0;
}
