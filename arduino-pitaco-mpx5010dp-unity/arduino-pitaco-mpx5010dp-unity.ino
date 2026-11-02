#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Update.h>
#include <math.h>
#include <Wire.h>
#include <MAX30105.h>
#include "heartRate.h"  // SparkFun: checkForBeat(IR)
#include <stdint.h>

// Gate 01 fica na segunda aba .ino; firmware respiratorio permanece central.
void g1Reset();
void g1Add(uint32_t red, uint32_t ir);
void g1MarkAcquisitionGap();
bool g1Evaluate(uint8_t* reason, uint16_t* samples);

// PITACO 2.0 - teste de integracao MPX5010DP + ESP32-C3
// Valores negativos representam variacao sob a referencia, NAO pressao
// diferencial negativa calibrada pelo fabricante do MPX5010DP.
#define DEBUG false
#define DEBUG_BT true
#define PORT_SENSOR 0
#define R1 2170.0f
#define R2 1500.0f
#define IS_WROOM_DA false
const float MPX_SUPPLY_V = 5.0f;        // Tolerancia de Vs influencia pressao quantitativa
const float ZERO_REFERENCE_PA = 100.0f; // Referencia provisoria para testar a Unity

#if IS_WROOM_DA // rotinas de redução de consumo relativas ao BT_SPP
#include "esp_bt_main.h"
#include "esp_bt.h"
#endif

// filtro média móvel com EMA
#define MOVING_AVERAGE true
#define EMA_ALPHA 0.35                                                      
// 100 para EMA sem média móvel, 20 para EMA com média móvel
// #define SAMPLESIZE 100
#define SAMPLESIZE 5

#define POTENCIA_BT ESP_PWR_LVL_P9

// UUIDs
#define SERVICE_UUID "0f128d4d-3cf9-46de-bb31-ed159450d6cf"
#define CHARACTERISTIC_UUID "3bcdff27-47fc-4a87-9684-7672c49d9266"
#define OTA_CONTROL_UUID "3bcdff28-47fc-4a87-9684-7672c49d9266"
#define OTA_DATA_UUID "3bcdff29-47fc-4a87-9684-7672c49d9266"
#define PPG_NOTIFY_UUID "3bcdff2a-47fc-4a87-9684-7672c49d9266"

// MAX30105: I2C ESP32-C3 PROVISORIO, conferir pinos fisicos.
#define MAX30105_SDA 4
#define MAX30105_SCL 5
#define PPG_WINDOW_MS 5000UL
#define PPG_POLL_GAP_MS 180UL
#define BLE_JSON_CHUNK_BYTES 20  // Compativel com MTU minimo de 23

// MPX5010DP nominal: Vout / Vs = 0.09 * P[kPa] + 0.04
const float RAZAO_DIV_TENSAO = (R1 + R2) / R2;
const float deadbandThreshold = 15.0f; // Experimental, ajustavel apos teste
 
// Controle do loop
unsigned long lastNotifyTime = 0;
const unsigned long notifyInterval = 50;

BLECharacteristic* pCharacteristic;
BLECharacteristic* pPpgCharacteristic = nullptr;
MAX30105 max30105;
bool ppgReady = false;
bool ppgSampling = false;
bool g1Ready = false;
bool g1Passed = false;
uint8_t g1Reason = 1;
uint16_t ppgSeq = 0;
uint16_t g1Window = 0;
unsigned long ppgWindowStartMs = 0;
unsigned long ppgLastPollMs = 0;
unsigned long lastBeatMs = 0;
float heartBpm = 0.0f;
float latestPressurePa = 0.0f;
bool pressureValid = false;
bool deviceConnected = false;
bool isCalibrated = false;
bool isSampling = false;
float calibrationOffsetPa = ZERO_REFERENCE_PA;
bool recalibrateZero = false;  // Comando c: recalibra repouso real
// Referencia dinamica preservada em RAM entre comandos e/r/f ate reinicio.
bool zeroReferenceValid = false;
bool zeroInProgress = false;
unsigned long zeroStartMs = 0;
unsigned long zeroLastSampleMs = 0;
unsigned int zeroCount = 0;
double zeroAccumPa = 0.0;
const unsigned long ZERO_WINDOW_MS = 10000UL;
const unsigned long ZERO_SAMPLE_INTERVAL_MS = 50UL;
const unsigned int ZERO_MIN_SAMPLES = 150;

#if MOVING_AVERAGE
int indexMovingAverage = 0;
float vals[SAMPLESIZE];
float sum = 0;
#endif

float emaValue = 0.0;
bool emaInitialized = false;

// Prototipos
float ReadRawPressurePa();
void Calibrate();
float voutToPa();
void ListenCommand(char cmd);
void ResetPressureFilter();
void SendStatus(const char* line);
void StartTenSecondZero();
void PollTenSecondZero();
void InitMAX30105();
void PollMAX30105();
void SendPpgJson(const char* jsonLine);
void SendG1Json(uint8_t reason, uint16_t samples);

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
#if DEBUG
    Serial.println("Client connected");
#endif
  }
  
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
#if DEBUG
    Serial.println("Cliente disconectado, reiniciando advertising...");
#endif
    pServer->getAdvertising()->start();
  }
};

class MyCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pChar) {
    deviceConnected = true; // State fallback: successful write guarantees active link
    String rxValue = pChar->getValue();
    if (rxValue.length() > 0) {
      char cmd = rxValue.charAt(0);
#if DEBUG
      Serial.print("Received command: ");
      Serial.println(cmd);
#endif
      ListenCommand(cmd);
    }
  }
};

BLECharacteristic* pOtaControlChar;
BLECharacteristic* pOtaDataChar;
bool isOtaUpdating = false;

class OtaControlCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pChar) {
    String val = pChar->getValue();
    if (val.length() == 0) return;
    uint8_t cmd = val[0];
    if (cmd == 0x01 && val.length() >= 5) { // START + 4 bytes size
      uint32_t fileSize = (uint8_t)val[1] | ((uint8_t)val[2] << 8) | ((uint8_t)val[3] << 16) | ((uint8_t)val[4] << 24);
      if (Update.begin(fileSize)) {
        isOtaUpdating = true;
        isSampling = false;
        Serial.printf("BLE OTA iniciado. Tamanho: %u bytes\n", fileSize);
        pOtaControlChar->setValue("OK_START\n");
        pOtaControlChar->notify();
      } else {
        Serial.println("Erro ao iniciar Update.begin()");
        pOtaControlChar->setValue("ERR_START\n");
        pOtaControlChar->notify();
      }
    } else if (cmd == 0x02) { // END
      if (Update.end(true)) {
        Serial.println("BLE OTA Concluido com sucesso! Reiniciando...");
        pOtaControlChar->setValue("OK_END\n");
        pOtaControlChar->notify();
        delay(1000);
        ESP.restart();
      } else {
        Serial.println("Erro ao finalizar Update.end()");
        pOtaControlChar->setValue("ERR_END\n");
        pOtaControlChar->notify();
      }
    } else if (cmd == 0x03) { // ABORT
      Update.abort();
      isOtaUpdating = false;
      pOtaControlChar->setValue("OK_ABORT\n");
      pOtaControlChar->notify();
    }
  }
};

class OtaDataCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pChar) {
    if (!isOtaUpdating) return;
    String rxData = pChar->getValue();
    size_t len = rxData.length();
    if (len > 0) {
      Update.write((uint8_t*)rxData.c_str(), len);
    }
  }
};

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

#if IS_WROOM_DA
  // ESP32 WROOM-DA apenas
  esp_bt_controller_mem_release(ESP_BT_MODE_IDLE);
#endif

  BLEDevice::setPower(POTENCIA_BT);
  BLEDevice::init("PITACO V2.0");
  BLEServer* pServer = BLEDevice::createServer();
  
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_NOTIFY);

  pCharacteristic->addDescriptor(new BLE2902());
  pCharacteristic->setCallbacks(new MyCallbacks());

  // Servico OTA BLE
  pOtaControlChar = pService->createCharacteristic(
    OTA_CONTROL_UUID,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_NOTIFY);
  pOtaControlChar->addDescriptor(new BLE2902());
  pOtaControlChar->setCallbacks(new OtaControlCallbacks());

  pOtaDataChar = pService->createCharacteristic(
    OTA_DATA_UUID,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  pOtaDataChar->setCallbacks(new OtaDataCallbacks());

  // Independente da caracteristica de pressao ja utilizada pelo PITACO.
  pPpgCharacteristic = pService->createCharacteristic(
    PPG_NOTIFY_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  pPpgCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->start();

  // Falha de MAX30105 nao interrompe o MPX5010DP.
  InitMAX30105();

#if DEBUG
  Serial.println("BLE service started, waiting for client...");
#endif
}

void loop() {
  // Escuta comandos via USB Serial
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'e' || c == 'E') {
      Serial.print("echop\n");
    }
    ListenCommand(c);
  }

#if DEBUG
  isSampling = true;
#endif

  // Atende FIFO regularmente, inclusive durante o zero de 10 segundos.
  PollMAX30105();

  // Nao emitir leituras enquanto calcula o zero; usar Pa sem filtros.
  if (zeroInProgress) {
    PollTenSecondZero();
    yield();
    return;
  }
  if (deviceConnected || isSampling) {
    if (isSampling && !isCalibrated) {
      Calibrate();
    }

    if (isSampling && isCalibrated) {
      unsigned long now = millis();
      if (now - lastNotifyTime >= notifyInterval) {
        lastNotifyTime = now;
        float rawPa = ReadRawPressurePa(); // filtro atualizado em 20 Hz

        float calibratedPa = rawPa - calibrationOffsetPa;
        
        // Aplica a deadband sobre o valor calibrado
        if (abs(calibratedPa) < deadbandThreshold) {
            calibratedPa = 0.0;
        }
        latestPressurePa = calibratedPa;
        pressureValid = true;
        // Formato numerico original mantido para clientes legados.
        char buf[32];
        snprintf(buf, sizeof(buf), "%.2f\n", calibratedPa);

        if (deviceConnected) {
          pCharacteristic->setValue(buf);
          pCharacteristic->notify();
        }

        // Transmite também via USB Serial (UART)
        Serial.print(buf);
      }
    }
  }
  yield(); // libera a task
}

void ListenCommand(char cmd) {
  if (cmd == 'e' || cmd == 'E') {
    if (zeroInProgress) {
      zeroInProgress = false; // handshake tem prioridade
      SendStatus("zero_cancelled\n");
    }
    if (isSampling) {
      isSampling = false;
      isCalibrated = false;
    }
    pCharacteristic->setValue("echop\n");
    pCharacteristic->notify();
  } else if (cmd == 'r' || cmd == 'R') {
    isSampling = true;
  } else if (cmd == 'f' || cmd == 'F') {
    isSampling = false;
    isCalibrated = false;
    recalibrateZero = false;
  } else if (cmd == 'c' || cmd == 'C') {
    recalibrateZero = true;
    isCalibrated = false;
  } else if (cmd == 'z' || cmd == 'Z') {
    StartTenSecondZero();
  }
}

void SendStatus(const char* line) {
  Serial.print(line);
  if (deviceConnected) {
    pCharacteristic->setValue(line);
    pCharacteristic->notify();
  }
}

void ResetPressureFilter() {
  const float inicial = voutToPa();
#if MOVING_AVERAGE
  sum = inicial * SAMPLESIZE;
  indexMovingAverage = 0;
  for (int i = 0; i < SAMPLESIZE; ++i) vals[i] = inicial;
#endif
  emaValue = inicial;
  emaInitialized = true;
}

void StartTenSecondZero() {
  if (zeroInProgress || isOtaUpdating) return;
  zeroInProgress = true;
  zeroStartMs = millis();
  zeroLastSampleMs = zeroStartMs;
  zeroCount = 0;
  zeroAccumPa = 0.0;
  SendStatus("zero_start\n");
}

void PollTenSecondZero() {
  const unsigned long now = millis();
  if (now - zeroLastSampleMs >= ZERO_SAMPLE_INTERVAL_MS) {
    zeroLastSampleMs = now;
    const float readingPa = voutToPa();
    if (isfinite(readingPa)) {
      zeroAccumPa += readingPa;
      ++zeroCount;
    }
  }
  if (now - zeroStartMs >= ZERO_WINDOW_MS) {
    zeroInProgress = false;
    if (zeroCount < ZERO_MIN_SAMPLES) {
      char reply[48];
      snprintf(reply, sizeof(reply), "zero_error:samples=%u\n", zeroCount);
      SendStatus(reply);
      return; // Preserva a referencia anterior.
    }
    calibrationOffsetPa = (float)(zeroAccumPa / zeroCount);
    zeroReferenceValid = true;
    recalibrateZero = false;
    ResetPressureFilter();
    isCalibrated = true;

    char reply[40];
    snprintf(reply, sizeof(reply), "zero_done:%.2f\n", calibrationOffsetPa);
    SendStatus(reply);
  }
}

// Retorna a pressão lida com filtro mas sem calibração e deadband
float ReadRawPressurePa() {
  float newVal = voutToPa();

#if MOVING_AVERAGE
  sum -= vals[indexMovingAverage];
  vals[indexMovingAverage] = newVal;
  sum += newVal;
  indexMovingAverage = (indexMovingAverage + 1) % SAMPLESIZE;
  float average = sum / SAMPLESIZE;

  if (!emaInitialized) {
    emaValue = average;
    emaInitialized = true;
  } else {
    emaValue = EMA_ALPHA * average + (1.0 - EMA_ALPHA) * emaValue;
  }
#else
  if (!emaInitialized) {
    emaValue = newVal;
    emaInitialized = true;
  } else {
    emaValue = EMA_ALPHA * newVal + (1.0 - EMA_ALPHA) * emaValue;
  }
#endif

  return emaValue;
}

void Calibrate() {
  // Primeira execucao: zero logico fixo 100 Pa.
  // Apos comando 'c': determina o zero real com tubo em repouso.
  if (recalibrateZero) {
    const int N = 60;
    float somaPa = 0.0f;
    for (int i = 0; i < N; ++i) {
      somaPa += voutToPa();
      delay(20); // ~1,2 s sem soprar ou inspirar
    }
    calibrationOffsetPa = somaPa / N;
    zeroReferenceValid = true;
  } else if (!zeroReferenceValid) {
    // Referencia fixa apenas enquanto nao houver calibracao real.
    calibrationOffsetPa = ZERO_REFERENCE_PA;
  }
  recalibrateZero = false;

  // Mantem referencia dinamica apos parada/reconexao da Unity.
  ResetPressureFilter();
  isCalibrated = true;
#if DEBUG
  Serial.printf("Calibrado. Offset (Pa): %.2f\n", calibrationOffsetPa);
#endif
}

float voutToPa() {
  // analogReadMilliVolts ja usa a calibracao disponivel do ADC no core.
  const float adcVoltage = analogReadMilliVolts(PORT_SENSOR) / 1000.0f;
  const float sensorVoltage = adcVoltage * RAZAO_DIV_TENSAO;
  const float pressaoKPa = (sensorVoltage / MPX_SUPPLY_V - 0.04f) / 0.09f;
  // A faixa negativa calculada nao e medida diferencial negativa validada.
  return pressaoKPa * 1000.0f;
}


// ---------------------------------------------------------------------------
// PITACO 2.4: MAX30105 RED/IR + frequencia cardiaca experimental.
// Um unico orquestrador .ino; G1 em gate_01_integrity.ino.
// ---------------------------------------------------------------------------
void InitMAX30105() {
  Wire.begin(MAX30105_SDA, MAX30105_SCL);
  if (!max30105.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("X,MAX30105_NOT_FOUND");
    return;
  }
  // RED+IR, 100 Hz com FIFO avg 4 (~25 amostras/s), largura 411us (18bits).
  max30105.setup(0x1F, 4, 2, 100, 411, 4096);
  max30105.setPulseAmplitudeRed(0x1F);
  max30105.setPulseAmplitudeIR(0x1F);
  max30105.setPulseAmplitudeGreen(0);
  max30105.disableFIFORollover();
  max30105.clearFIFO();
  g1Reset();
  ppgReady = true;
  Serial.println("X,MAX30105_READY,RED_IR");
}

// A caracteristica de pressao original continua transmitindo 20 Hz;
// o canal PPG transporta JSONL. Fracionar em 20B para MTU GATT minimo.
// Receptor junta bytes ate o LF. Validar throughput real antes de producao.
void SendPpgJson(const char* jsonLine) {
  Serial.print(jsonLine);
  if (!deviceConnected || !pPpgCharacteristic) return;
  const size_t n = strlen(jsonLine);
  for (size_t off = 0; off < n; off += BLE_JSON_CHUNK_BYTES) {
    const size_t len = (n - off > BLE_JSON_CHUNK_BYTES)
                         ? BLE_JSON_CHUNK_BYTES : n - off;
    pPpgCharacteristic->setValue((uint8_t*)(jsonLine + off), len);
    pPpgCharacteristic->notify();
  }
}

void SendG1Json(uint8_t reason, uint16_t samples) {
  char line[160];
  snprintf(line, sizeof(line),
           "{\"type\":\"g1\",\"t_ms\":%lu,\"window\":%u,\"sqi\":{\"g1\":%s,\"reason\":%u,\"samples\":%u}}\n",
           millis(), (unsigned)g1Window, reason == 0 ? "true" : "false",
           (unsigned)reason, (unsigned)samples);
  SendPpgJson(line);
}

void PollMAX30105() {
  if (!ppgReady) return;
  const bool enabled = isSampling && isCalibrated && !isOtaUpdating;

  if (!enabled) {
    if (ppgSampling) {
      ppgSampling = false;
      max30105.clearFIFO();
      g1Reset();
      g1Ready = false;
      g1Passed = false;
      heartBpm = 0;
      lastBeatMs = 0;
    }
    return;
  }

  const unsigned long now = millis();
  if (!ppgSampling) {
    max30105.clearFIFO();
    g1Reset();
    ppgSampling = true;
    ppgWindowStartMs = now;
    ppgLastPollMs = now;
    g1Ready = false;
    g1Passed = false;
    g1Reason = 1;
    heartBpm = 0;
    lastBeatMs = 0;
    ++g1Window;
  } else if ((unsigned long)(now - ppgLastPollMs) > PPG_POLL_GAP_MS) {
    // Marcar a janela invalida apos pausa, ainda que o FIFO tenha amostras.
    g1MarkAcquisitionGap();
  }
  ppgLastPollMs = now;

  max30105.check();
  while (max30105.available()) {
    const uint32_t red = max30105.getFIFORed();
    const uint32_t ir = max30105.getFIFOIR();
    const unsigned long receiveMs = millis(); // leitura FIFO, nao timestamp ADC
    ++ppgSeq;
    g1Add(red, ir);

    // checkForBeat(IR) da SparkFun: BPM e estimativa experimental.
    // Nunca fornecer BPM como valido antes de G1 PASS.
    // SparkFun heartRate.cpp utiliza uint16_t e int16_t internamente.
    // Normalizar 18-bit -> 15-bit apenas para BPM: RAW permanece 18-bit.
    if (ir > 5000 && checkForBeat((int32_t)(ir >> 3))) {
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

    const bool bpmValid = g1Ready && g1Passed && heartBpm > 0
                       && lastBeatMs > 0
                       && (unsigned long)(receiveMs - lastBeatMs) <= 2000UL;
    char bpm[16];
    if (bpmValid) snprintf(bpm, sizeof(bpm), "%.1f", heartBpm);
    else strcpy(bpm, "null");

    // JSON por linha: mesmo esquema USB / BLE, sem dependencias de ArduinoJson.
    // Pressao amostrada a 20Hz; RED/IR, cerca de 25Hz efetivos.
    // G1 usa o ultimo resultado de uma janela de 5 segundos.
    char line[240];
    const int written = snprintf(line, sizeof(line),
        "{\"type\":\"sample\",\"seq\":%u,\"t_ms\":%lu,"
        "\"ppg\":{\"red\":%lu,\"ir\":%lu,\"bpm\":%s,\"bpm_valid\":%s},"
        "\"mpx5010dp\":{\"pressure_pa\":%.2f,\"valid\":%s},"
        "\"sqi\":{\"g1\":%s,\"reason\":%u}}\n",
        (unsigned)ppgSeq, receiveMs, (unsigned long)red,
        (unsigned long)ir, bpm, bpmValid ? "true" : "false",
        latestPressurePa, pressureValid ? "true" : "false",
        g1Ready ? (g1Passed ? "true" : "false") : "null",
        (unsigned)g1Reason);
    if (written > 0 && written < (int)sizeof(line)) SendPpgJson(line);
    max30105.nextSample();
  }

  if ((unsigned long)(millis() - ppgWindowStartMs) >= PPG_WINDOW_MS) {
    uint16_t samples = 0;
    uint8_t reason = 1;
    g1Passed = g1Evaluate(&reason, &samples);
    g1Reason = reason;
    g1Ready = true;
    SendG1Json(reason, samples);
    g1Reset();
    ppgWindowStartMs = millis();
    ++g1Window;
  }
}
