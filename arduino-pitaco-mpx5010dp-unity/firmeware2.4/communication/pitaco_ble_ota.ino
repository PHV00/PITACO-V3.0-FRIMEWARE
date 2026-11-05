// SoC: BLE, comunicacao USB, OTA e publicacao de bytes existentes.
// Protocolo, UUIDs, tamanho dos fragmentos e callbacks preservados.

// BLE legado: estado da conexao; reinicia advertising apos desconexao.
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

// BLE legado: recebe comandos na characteristic original da pressao.
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

// OTA legado: comandos START, END e ABORT.
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

// OTA legado: grava os blocos recebidos durante atualizacao.
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

// Inicializacao BLE antes contida em setup().
void InitBleCommunication() {
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
}

// Status simultaneo via USB e characteristic BLE de pressao.
void SendStatus(const char* line) {
  Serial.print(line);
  if (deviceConnected) {
    pCharacteristic->setValue(line);
    pCharacteristic->notify();
  }
}

// A caracteristica de pressao original continua transmitindo 20 Hz;
// o canal PPG transporta JSONL. Fracionar em 20B para MTU GATT minimo.
// Receptor junta bytes ate o LF. Validar throughput real antes de producao.
// Envia JSONL em USB e fragmentos BLE de ate 20 bytes por notificacao.
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
