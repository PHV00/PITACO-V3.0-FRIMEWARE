#include "ppg_max30102.h"
#include "sqi_gate1.h"
#include <Arduino.h>
#include <Wire.h>
#include <MAX30105.h>
#include <BLEDevice.h>

// 100 Hz e FIFO average=4 devem resultar em ~25 amostras/s efetivas.
static const uint32_t WINDOW_MS = 5000UL;
static const uint32_t GAP_ALERT_MS = 180UL;
static MAX30105 sensor;
static BLECharacteristic* notifyCharacteristic = nullptr;
static bool sensorReady = false, wasSampling = false;
static uint16_t sequence = 0, windowId = 0;
static uint32_t windowStart = 0, lastPoll = 0;

static void u16(uint8_t* p, uint16_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}
static void u32(uint8_t* p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static void u18(uint8_t* p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16);
}
static void sendSample(uint32_t red, uint32_t ir, uint32_t ts, bool connected) {
  ++sequence;
  // USB: R,seq,receive_ms,window,red,ir
  Serial.printf("R,%u,%lu,%u,%lu,%lu\n", (unsigned)sequence,
       (unsigned long)ts, (unsigned)windowId, (unsigned long)red, (unsigned long)ir);
  // BLE 16 B: A5 01 | seq:u16 | window:u16 | ts_ms:u32 | red:u24 | ir:u24
  if (connected && notifyCharacteristic) {
    uint8_t packet[16] = {};
    packet[0] = 0xA5; packet[1] = 1;
    u16(packet+2, sequence); u16(packet+4, windowId); u32(packet+6, ts);
    u18(packet+10, red); u18(packet+13, ir);
    notifyCharacteristic->setValue(packet, sizeof(packet));
    notifyCharacteristic->notify();
  }
}
static void sendQuality(const G1Result& g1, uint32_t ts, bool connected) {
  // USB: Q,window,end_ms,pass,reason,samples
  Serial.printf("Q,%u,%lu,%u,%u,%u\n", (unsigned)windowId,
       (unsigned long)ts, g1.passed ? 1u : 0u,
       (unsigned)g1.reason, (unsigned)g1.samples);
  // BLE 12 B: A5 02 | window:u16 | end_ms:u32 | pass:u8 | reason:u8 | samples:u16
  if (connected && notifyCharacteristic) {
    uint8_t packet[12] = {};
    packet[0] = 0xA5; packet[1] = 2;
    u16(packet+2, windowId); u32(packet+4, ts);
    packet[8] = g1.passed ? 1 : 0; packet[9] = g1.reason;
    u16(packet+10, g1.samples);
    notifyCharacteristic->setValue(packet, sizeof(packet));
    notifyCharacteristic->notify();
  }
}
void ppgBegin(BLECharacteristic* ppgNotifyCharacteristic) {
  notifyCharacteristic = ppgNotifyCharacteristic;
  Wire.begin(PITACO24_I2C_SDA, PITACO24_I2C_SCL);
  if (!sensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("X,PPG_ERROR,MAX30102_NOT_FOUND");
    return; // O PITACO segue funcionando sem MAX30102.
  }
  sensor.setup(0x1F, 4, 2, 100, 411, 4096);
  sensor.setPulseAmplitudeRed(0x1F);
  sensor.setPulseAmplitudeIR(0x1F);
  sensor.setPulseAmplitudeGreen(0);
  sensor.disableFIFORollover();
  sensor.clearFIFO();
  g1Reset();
  sensorReady = true;
  Serial.println("X,PPG_READY,G1_ONLY");
}
void ppgPoll(bool allowSampling, bool connected) {
  if (!sensorReady) return;
  if (!allowSampling) {
    if (wasSampling) {
      wasSampling = false;
      sensor.clearFIFO();
      g1Reset();
    }
    return;
  }
  const uint32_t now = millis();
  if (!wasSampling) {
    sensor.clearFIFO(); // Descartar amostras pre-r e da calibracao.
    g1Reset();
    windowStart = now;
    lastPoll = now;
    wasSampling = true;
    ++windowId;
  } else if ((uint32_t)(now - lastPoll) > GAP_ALERT_MS) {
    // Biblioteca SparkFun tem buffer interno curto: rejeitar janela suspeita.
    g1MarkAcquisitionGap();
  }
  lastPoll = now;
  sensor.check();
  while (sensor.available()) {
    const uint32_t red = sensor.getFIFORed();
    const uint32_t ir = sensor.getFIFOIR();
    const uint32_t receivedAt = millis(); // nao timestamp ADC
    g1Add(red, ir);
    sendSample(red, ir, receivedAt, connected);
    sensor.nextSample();
  }
  if ((uint32_t)(millis() - windowStart) >= WINDOW_MS) {
    const uint32_t ended = millis();
    const G1Result g1 = g1Evaluate();
    sendQuality(g1, ended, connected);
    g1Reset();
    windowStart = ended;
    ++windowId;
  }
}
