#pragma once

// PITACO 2.4 — sensor fisico MAX30105; biblioteca SparkFun MAX3010x.
// MAX30105 possui RED, IR e GREEN. SQI Gate 01 usa apenas RED/IR.
// 0 = somente RED + IR (padrao para PPG / oxi experimental).
// 1 = RED + IR + GREEN (diagnostico opcional, nao entra no G1).
#ifndef PITACO24_ENABLE_GREEN
#define PITACO24_ENABLE_GREEN 0
#endif

#if PITACO24_ENABLE_GREEN != 0 && PITACO24_ENABLE_GREEN != 1
#error "PITACO24_ENABLE_GREEN must be 0 or 1"
#endif

// Pinos ESP32-C3 provisórios do RFC; verificar pinagem e alimentacao!
// Sensor de pressao da branch personalizada permanece em GPIO0.
#ifndef PITACO24_I2C_SDA
#define PITACO24_I2C_SDA 4
#endif
#ifndef PITACO24_I2C_SCL
#define PITACO24_I2C_SCL 5
#endif

class BLECharacteristic;
void ppgBegin(BLECharacteristic* ppgNotifyCharacteristic);
void ppgPoll(bool allowSampling, bool bleConnected);
