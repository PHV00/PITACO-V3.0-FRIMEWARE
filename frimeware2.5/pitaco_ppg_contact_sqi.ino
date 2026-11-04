// SoC: contato optico, estado de validade e avaliacao periodica do G1.
// As estatisticas/thresholds do G1 permanecem em gate_01_integrity.ino.

// Reinicia o detector optico de contato, separado do Gate 01.
void ResetPpgContact() {
  ppgContactPresent = false;
  ppgContactGoodSamples = 0;
  ppgContactBadSamples = 0;
}

bool UpdatePpgContact(uint32_t red, uint32_t ir, unsigned long receiveMs) {
    // A aptidao optica independe do resultado de G1 calculado a cada 5s.
    // Tres amostras consecutivas confirmam a mudanca de contato.
    const bool opticalPresent = red >= PPG_CONTACT_MIN && ir >= PPG_CONTACT_MIN
                                && red < (262143UL - 2048UL)
                                && ir < (262143UL - 2048UL);
    if (opticalPresent) {
      ppgContactBadSamples = 0;
      if (ppgContactGoodSamples < PPG_CONTACT_CONFIRM_SAMPLES)
        ++ppgContactGoodSamples;
      if (!ppgContactPresent &&
          ppgContactGoodSamples >= PPG_CONTACT_CONFIRM_SAMPLES) {
        ppgContactPresent = true;
        // Exigir janela NOVA apos retomar contato: nao herdar PASS antigo.
        g1Reset();
        ppgWindowStartMs = receiveMs;
        g1Ready = false;
        g1Passed = false;
        g1Reason = 1;
        heartBpm = 0.0f;
        lastBeatMs = 0;
        Serial.println("X,PPG_CONTACT,PRESENT");
      }
    } else {
      ppgContactGoodSamples = 0;
      if (ppgContactBadSamples < PPG_CONTACT_CONFIRM_SAMPLES)
        ++ppgContactBadSamples;
      if (ppgContactPresent &&
          ppgContactBadSamples >= PPG_CONTACT_CONFIRM_SAMPLES) {
        ppgContactPresent = false;
        // Descartar janela mista; manter RAW disponivel para diagnostico.
        g1Reset();
        ppgWindowStartMs = receiveMs;
        g1Ready = false;
        g1Passed = false;
        g1Reason = 10;
        heartBpm = 0.0f;
        lastBeatMs = 0;
        Serial.println("X,PPG_CONTACT,ABSENT");
      }
    }
    return opticalPresent;
}

void PollPpgGateWindow() {
  if ((unsigned long)(millis() - ppgWindowStartMs) >= PPG_WINDOW_MS) {
    uint16_t samples = 0;
    uint8_t reason = 1;
    g1Passed = g1Evaluate(&reason, &samples);
    if (!ppgContactPresent) {
      // Uma janela sem contato nunca deve emitir G1 PASS, mesmo que
      // os thresholds estatisticos sejam enganados por luminosidade.
      if (reason == 0) reason = 10;  // CONTACT_ABSENT
      g1Passed = false;
    }
    g1Reason = reason;
    g1Ready = true;
    SendG1Json(reason, samples);
    g1Reset();
    ppgWindowStartMs = millis();
    ++g1Window;
  }
}
