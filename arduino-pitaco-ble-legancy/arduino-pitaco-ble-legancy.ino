#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Update.h>

// ESP32 WROOM-DA apenas
#define DEBUG false
#define DEBUG_BT true 
#define PORT_SENSOR 0
#define R1 1800.0
#define R2 3300.0
#define IS_WROOM_DA false

#if IS_WROOM_DA // rotinas de redução de consumo relativas ao BT_SPP
#include "esp_bt_main.h"
#include "esp_bt.h"
#endif

// filtro média móvel com EMA
#define MOVING_AVERAGE true
#define EMA_ALPHA 0.02                                                      
// 100 para EMA sem média móvel, 20 para EMA com média móvel
// #define SAMPLESIZE 100
#define SAMPLESIZE 20

#define POTENCIA_BT ESP_PWR_LVL_P9

// UUIDs
#define SERVICE_UUID "0f128d4d-3cf9-46de-bb31-ed159450d6cf"
#define CHARACTERISTIC_UUID "3bcdff27-47fc-4a87-9684-7672c49d9266"
#define OTA_CONTROL_UUID "3bcdff28-47fc-4a87-9684-7672c49d9266"
#define OTA_DATA_UUID "3bcdff29-47fc-4a87-9684-7672c49d9266"

// Parâmetros do Sensor
const float Vmin = 0.5;
const float Vmax = 4.5;
const float Pmin = -5000.0;
const float Pmax = 5000.0;
const float RAZAO_DIV_TENSAO = (R1 + R2) / R2;
const float RAZAO_ESCALA_PRESSAO = (Pmax - Pmin) / (Vmax - Vmin);
const float deadbandThreshold = 15.0; // Deadband em Pascals
 
// Controle do loop
unsigned long lastNotifyTime = 0;
const unsigned long notifyInterval = 50;

BLECharacteristic* pCharacteristic;
bool deviceConnected = false;
bool isCalibrated = false;
bool isSampling = false;
float calibrationOffsetPa = 0.0;

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
float voutToPa(int adcReading);
void ListenCommand(char cmd);

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    Serial.println("Client connected");
  }
  
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    Serial.println("Cliente disconectado, reiniciando advertising...");
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

  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->start();

  Serial.println("BLE service started, waiting for client...");
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

  if (deviceConnected || isSampling) {
    if (isSampling && !isCalibrated) {
      Calibrate();
    }

    if (isSampling && isCalibrated) {
      float rawPa = ReadRawPressurePa();
      unsigned long now = millis();

      if (now - lastNotifyTime >= notifyInterval) {
        lastNotifyTime = now;

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
  } else if (cmd == 'c' || cmd == 'C') {
    isCalibrated = false;
  }
}

// Retorna a pressão lida com filtro mas sem calibração e deadband
float ReadRawPressurePa() {
  float newVal = voutToPa(analogRead(PORT_SENSOR));

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
  float rawReading = voutToPa(analogRead(PORT_SENSOR));
  
  // preenchendo o buffer com valores iniciais
#if MOVING_AVERAGE
  for (int i = 0; i < SAMPLESIZE; i++) {
    vals[i] = rawReading;
  }
  sum = rawReading * SAMPLESIZE;
  indexMovingAverage = 0;
#endif

  emaValue = rawReading;
  emaInitialized = true;

  // leitura inicial
  for (int i = 0; i < SAMPLESIZE; i++) {
    ReadRawPressurePa();
    yield(); 
  }
  
  float currentSum = 0.0;
  // tirando a média real
  for (int i = 0; i < SAMPLESIZE; i++) {
    currentSum += ReadRawPressurePa();
    yield();
  }

  calibrationOffsetPa = currentSum / SAMPLESIZE;
  isCalibrated = true;
  Serial.printf("Calibrado. Offset (Pa): %.2f\n", calibrationOffsetPa);
}

float voutToPa(int adcReading) {
  float adcVoltage = (adcReading / 4095.0) * 3.3;
  float sensorVoltage = adcVoltage * RAZAO_DIV_TENSAO;

  if (sensorVoltage < Vmin) sensorVoltage = Vmin;
  else if (sensorVoltage > Vmax) sensorVoltage = Vmax;

  return Pmin + (sensorVoltage - Vmin) * RAZAO_ESCALA_PRESSAO;
}