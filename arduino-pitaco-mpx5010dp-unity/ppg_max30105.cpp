#include "ppg_max30105.h"
#include "sqi_gate1.h"

#include <Arduino.h>
#include <Wire.h>
#include <MAX30105.h>
#include <BLEDevice.h>

// Configuracao de partida (MAX30105): 100 Hz, FIFO-average 4,
// resolucao 18 bits, janela G1 de 5 s. Medir taxa efetiva em bancada.
static const uint32_t WINDOW_MS = 5000UL;
static const uint32_t GAP_ALERT_MS = 180UL;
static const uint8_t LED_MODE = PITACO24_ENABLE_GREEN ? 3 : 2;

static MAX30105 sensor;
static BLECharacteristic* notifyCharacteristic = nullptr;
static bool sensorReady = false;
static bool wasSampling = false;
static uint16_t sequence = 0;
static uint16_t windowId = 0;
static uint32_t windowStart = 0;
static uint32_t lastPoll = 0;

static void u16(uint8_t* p, uint16_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}
static void u32(uint8_t* p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static void u18(uint8_t* p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)(v >> 16);
}

static void sendSample(uint32_t red, uint32_t ir, uint32_t green,
                       uint32_t ts, bool connected) {
  ++sequence;
  if (PITACO24_ENABLE_GREEN) {
    // USB: R,seq,receive_ms,window,red,ir,green
    Serial.printf("R,%u,%lu,%u,%lu,%lu,%lu\n", (unsigned)sequence,
                  (unsigned long)ts, (unsigned)windowId,
                  (unsigned long)red, (unsigned long)ir,
                  (unsigned long)green);
  } else {
    // USB: R,seq,receive_ms,window,red,ir
    Serial.printf("R,%u,%lu,%u,%lu,%lu\n", (unsigned)sequence,
                  (unsigned long)ts, (unsigned)windowId,
                  (unsigned long)red, (unsigned long)ir);
  }

  if (!connected || !notifyCharacteristic) return;

  if (PITACO24_ENABLE_GREEN) {
    // BLE 19 bytes: A5 03 | seq:u16 | window:u16 | ms:u32 |
    // red:u24 | ir:u24 | green:u24 (cabe no payload ATT de 20 bytes).
    uint8_t packet[19] = {};
    packet[0] = 0xA5; packet[1] = 0x03;
    u16(packet + 2, sequence);
    u16(packet + 4, windowId);
    u32(packet + 6, ts);
    u18(packet + 10, red);
    u18(packet + 13, ir);
    u18(packet + 16, green);
    notifyCharacteristic->setValue(packet, sizeof(packet));
    notifyCharacteristic->notify();
  } else {
    // BLE 16 bytes, protocolo do prototipo anterior:
    // A5 01 | seq:u16 | window:u16 | ms:u32 | red:u24 | ir:u24
    uint8_t packet[16] = {};
    packet[0] = 0xA5; packet[1] = 0x01;
    u16(packet + 2, sequence);
    u16(packet + 4, windowId);
    u32(packet + 6, ts);
    u18(packet + 10, red);
    u18(packet + 13, ir);
    notifyCharacteristic->setValue(packet, sizeof(packet));
    notifyCharacteristic->notify();
  }
}

static void sendQuality(const G1Result& g1, uint32_t ts, bool connected) {
  Serial.printf("Q,%u,%lu,%u,%u,%u\n", (unsigned)windowId,
                (unsigned long)ts, g1.passed ? 1u : 0u,
                (unsigned)g1.reason, (unsigned)g1.samples);
  if (connected && notifyCharacteristic) {
    // BLE 12 bytes: A5 02 | window:u16 | ms:u32 |
    // pass:u8 | reason:u8 | count:u16
    uint8_t packet[12] = {};
    packet[0] = 0xA5; packet[1] = 0x02;
    u16(packet + 2, windowId); u32(packet + 4, ts);
    packet[8] = g1.passed ? 1 : 0;
    packet[9] = g1.reason;
    u16(packet + 10, g1.samples);
    notifyCharacteristic->setValue(packet, sizeof(packet));
    notifyCharacteristic->notify();
  }
}

void ppgBegin(BLECharacteristic* ppgNotifyCharacteristic) {
  notifyCharacteristic = ppgNotifyCharacteristic;
  Wire.begin(PITACO24_I2C_SDA, PITACO24_I2C_SCL);

  if (!sensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("X,PPG_ERROR,MAX30105_NOT_FOUND");
    return; // Sensor ausente nao desabilita a pressao.
  }

  // PART_ID 0x15 e compartilhado com MAX30102: NAO identifica o modelo.
  Serial.printf("X,PPG_IDENT,MAX30105_ASSUMED,PART_ID,0x%02X,REV,0x%02X\n",
                (unsigned)sensor.readPartID(),
                (unsigned)sensor.getRevisionID());

  // SparkFun: ledMode=2 RED+IR, ledMode=3 RED+IR+GREEN.
  sensor.setup(0x1F, 4, LED_MODE, 100, 411, 4096);
  sensor.setPulseAmplitudeRed(0x1F);
  sensor.setPulseAmplitudeIR(0x1F);
  sensor.setPulseAmplitudeGreen(PITACO24_ENABLE_GREEN ? 0x1F : 0);
  sensor.disableFIFORollover();
  sensor.clearFIFO();

  g1Reset();
  sensorReady = true;
  Serial.printf("X,PPG_READY,MAX30105,CHANNELS,%s,G1_ONLY\n",
                PITACO24_ENABLE_GREEN ? "RED_IR_GREEN" : "RED_IR");
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
    sensor.clearFIFO();
    g1Reset();
    windowStart = now;
    lastPoll = now;
    wasSampling = true;
    ++windowId;
  } else if ((uint32_t)(now - lastPoll) > GAP_ALERT_MS) {
    // Verificacao conservadora; NAO detecta todas as perdas de FIFO.
    g1MarkAcquisitionGap();
  }
  lastPoll = now;

  sensor.check();
  while (sensor.available()) {
    const uint32_t red = sensor.getFIFORed();
    const uint32_t ir = sensor.getFIFOIR();
    const uint32_t green =
        PITACO24_ENABLE_GREEN ? sensor.getFIFOGreen() : 0UL;
    const uint32_t receivedAt = millis(); // momento de leitura do FIFO
    g1Add(red, ir);
    sendSample(red, ir, green, receivedAt, connected);
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
