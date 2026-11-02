#pragma once
class BLECharacteristic;
// Valores provisórios para placa ESP32-C3 de referencia; verificar pinos reais.
// Sensor de pressao utiliza GPIO0 na branch do PITACO.
#ifndef PITACO24_I2C_SDA
#define PITACO24_I2C_SDA 4
#endif
#ifndef PITACO24_I2C_SCL
#define PITACO24_I2C_SCL 5
#endif
void ppgBegin(BLECharacteristic* ppgNotifyCharacteristic);
void ppgPoll(bool allowSampling, bool bleConnected);
