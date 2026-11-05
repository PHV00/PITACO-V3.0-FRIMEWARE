// SoC: serializacao de telemetria optica RED/IR e eventos G1.
// O transporte de bytes USB/BLE permanece em pitaco_ble_ota.ino.

// Publica o resultado periodico da janela G1, sem alterar RAW.
void SendG1Json(uint8_t reason, uint16_t samples) {
  char line[160];
  snprintf(line, sizeof(line),
           "{\"type\":\"g1\",\"t_ms\":%lu,\"window\":%u,\"sqi\":{\"g1\":%s,\"reason\":%u,\"samples\":%u}}\n",
           millis(), (unsigned)g1Window, reason == 0 ? "true" : "false",
           (unsigned)reason, (unsigned)samples);
  SendPpgJson(line);
}

void PublishPpgSample(uint32_t red, uint32_t ir,
                      unsigned long receiveMs, bool opticalPresent) {
    // Tambem bloquear envio imediato se esta amostra perder o contato
    // optico, sem esperar o fim da proxima janela G1.
    const bool instantContact = ppgContactPresent && opticalPresent;
    const bool bpmValid = IsPpgBpmValid(receiveMs, instantContact);
    char bpm[16];
    if (bpmValid) snprintf(bpm, sizeof(bpm), "%.1f", heartBpm);
    else strcpy(bpm, "null");

    // Nao divulgar G1 PASS antigo enquanto a amostra atual for inadequada.
    // reason=10 e exclusivo do JSON de amostras: CONTACT_ABSENT.
    const char* effectiveG1 = !instantContact ? "false" :
                              (g1Ready ? (g1Passed ? "true" : "false") : "null");
    const uint8_t effectiveReason = instantContact ? g1Reason : 10;

    // JSON por linha: mesmo esquema USB / BLE, sem dependencias de ArduinoJson.
    // Pressao amostrada a 20Hz; RED/IR, cerca de 25Hz efetivos.
    // G1 usa o ultimo resultado de uma janela de 5 segundos.
    char line[240];
    const int written = snprintf(line, sizeof(line),
        "{\"type\":\"sample\",\"seq\":%u,\"t_ms\":%lu,"
        "\"ppg\":{\"red\":%lu,\"ir\":%lu,\"bpm\":%s,\"bpm_valid\":%s},"
        "\"mpx5010dp\":{\"pressure_pa\":%.2f,\"valid\":%s},"
        "\"sqi\":{\"g1\":%s,\"reason\":%u,\"contact\":%s}}\n",
        (unsigned)ppgSeq, receiveMs, (unsigned long)red,
        (unsigned long)ir, bpm, bpmValid ? "true" : "false",
        latestPressurePa, pressureValid ? "true" : "false",
        effectiveG1, (unsigned)effectiveReason,
        instantContact ? "true" : "false");
    if (written > 0 && written < (int)sizeof(line)) SendPpgJson(line);
}
