// O mesmo Gate usado pelo firmware e compilado no host como C++ puro.
#include "../gate_01_integrity.ino"
#include <assert.h>
#include <stdio.h>

static void expect(uint8_t code) {
  uint8_t reason = 255;
  uint16_t count = 0;
  const bool passed = g1Evaluate(&reason, &count);
  assert(reason == code);
  assert(passed == (code == 0));
}
int main() {
  g1Reset();
  for (unsigned i=0; i<125; ++i)
    g1Add(106000u+(i%7u)*250u, 118000u+(i%9u)*350u);
  expect(0);
  g1Reset();
  for (unsigned i=0; i<125; ++i) g1Add(600u+i%20u,550u+i%15u);
  expect(2);
  g1Reset();
  for (unsigned i=0; i<125; ++i) g1Add(100000u,120000u+i*20u);
  expect(4);
  g1Reset();
  for (unsigned i=0; i<125; ++i)
    g1Add(i==50?262143u:106000u+(i%5u)*200u,118000u+(i%7u)*220u);
  expect(6);
  g1Reset();
  for (unsigned i=0; i<10; ++i) g1Add(100000u+i*120u,120000u+i*110u);
  expect(8);
  g1Reset();
  for (unsigned i=0; i<125; ++i)
    g1Add(106000u+(i%5u)*200u,118000u+(i%7u)*220u);
  g1MarkAcquisitionGap();
  expect(9);
  g1Reset();
  expect(1);
  puts("PASS: 7 G1 host scenarios");
  return 0;
}
