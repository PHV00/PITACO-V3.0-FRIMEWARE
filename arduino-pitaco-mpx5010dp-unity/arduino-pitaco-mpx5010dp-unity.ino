#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Update.h>
#include <math.h>
#include <Wire.h>
// Driver SparkFun local: buffer 64 slots e leitura FIFO protegida.
#include "src/vendor_sparkfun_max3010x/MAX30105.h"
#include "src/vendor_sparkfun_max3010x/heartRate.h" // checkForBeat(IR)
#include <stdint.h>

// SoC por abas .ino: o Arduino concatena os arquivos no mesmo sketch.
// Configuracoes e estados globais compartilhados permanecem aqui.
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
#define PPG_CONTACT_MIN 5000UL  // provisorio, depende de ensaio
#define PPG_CONTACT_CONFIRM_SAMPLES 3
#define PPG_DIAG true  // Telemetria de bancada a cada 2s; desligar apos validacao
#define PPG_DIAG_MS 2000UL
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
bool ppgContactPresent = false;
uint8_t ppgContactGoodSamples = 0;
uint8_t ppgContactBadSamples = 0;
uint16_t ppgBeatDetections = 0;
bool g1Ready = false;
bool g1Passed = false;
uint8_t g1Reason = 1;
uint16_t ppgSeq = 0;
uint16_t g1Window = 0;
unsigned long ppgWindowStartMs = 0;
unsigned long ppgLastPollMs = 0;
unsigned long ppgLastDiagMs = 0;
uint32_t ppgDiagFound = 0;
uint32_t ppgDiagProcessed = 0;
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
void ResetPpgContact();
void InitMAX30105();
void PollMAX30105();
void SendPpgJson(const char* jsonLine);
void SendG1Json(uint8_t reason, uint16_t samples);

// Interfaces entre as abas; implementacoes em seus modulos SoC.
void InitBleCommunication();
void PollPressureSampling();
bool UpdatePpgContact(uint32_t red, uint32_t ir, unsigned long receiveMs);
void ProcessPpgBeat(uint32_t ir, unsigned long receiveMs, bool opticalPresent);
bool IsPpgBpmValid(unsigned long receiveMs, bool instantContact);
void PublishPpgSample(uint32_t red, uint32_t ir, unsigned long receiveMs, bool opticalPresent);
void PollPpgGateWindow();

// Orquestrador central: organiza ciclo de vida sem implementar sensores.
// Inicializa pressao/USB/BLE/OTA e adiciona PPG sem substituir o legado.
void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

#if IS_WROOM_DA
  // ESP32 WROOM-DA apenas
  esp_bt_controller_mem_release(ESP_BT_MODE_IDLE);
#endif

  InitBleCommunication();

  // Falha de MAX30105 nao interrompe o MPX5010DP.
  InitMAX30105();

#if DEBUG
  Serial.println("BLE service started, waiting for client...");
#endif
}

// Orquestra comandos, aquisicao PPG e a leitura de pressao do PITACO.
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
  PollPressureSampling();
  yield(); // libera a task
}
