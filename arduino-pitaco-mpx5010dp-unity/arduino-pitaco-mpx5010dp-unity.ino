#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Update.h>
#include <math.h>
#include "ppg_max30105.h"  // PITACO 2.4: MAX30105 + SQI Gate 01

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

// MPX5010DP nominal: Vout / Vs = 0.09 * P[kPa] + 0.04
const float RAZAO_DIV_TENSAO = (R1 + R2) / R2;
const float deadbandThreshold = 15.0f; // Experimental, ajustavel apos teste
 
// Controle do loop
unsigned long lastNotifyTime = 0;
const unsigned long notifyInterval = 50;

BLECharacteristic* pCharacteristic;
BLECharacteristic* pPpgCharacteristic = nullptr;
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

  // Falha do sensor PPG nao pode desabilitar a pressao.
  ppgBegin(pPpgCharacteristic);

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

  // Coleta nao bloqueante; so inicia PPG apos calibracao inicial de pressao.
  // Continua lendo PPG durante o zero de 10 s.
  ppgPoll(isSampling && isCalibrated && !isOtaUpdating, deviceConnected);

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
        // formata e envia a leitura para buf
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
