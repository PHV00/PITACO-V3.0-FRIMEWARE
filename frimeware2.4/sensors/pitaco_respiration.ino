// SoC: pressao MPX5010DP, filtros, calibracao e zero de 10 s.
// Frequencia, valores e saida serial numerica mantidos.

// Tarefa de 20 Hz antes contida diretamente no loop().
void PollPressureSampling() {
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
}

// Reinicia EMA e media movel apos a mudanca de referencia.
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

// Inicia coleta do zero do MPX durante dez segundos.
void StartTenSecondZero() {
  if (zeroInProgress || isOtaUpdating) return;
  zeroInProgress = true;
  zeroStartMs = millis();
  zeroLastSampleMs = zeroStartMs;
  zeroCount = 0;
  zeroAccumPa = 0.0;
  SendStatus("zero_start\n");
}

// Calcula nova referencia em Pa com amostras sem filtro.
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
// Faz a filtragem MPX, antes de offset e deadband.
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

// Gerencia zero fixo provisorio ou calibracao por comando c.
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

// ADC MPX5010DP e conversao experimental de tensao em Pa.
float voutToPa() {
  // analogReadMilliVolts ja usa a calibracao disponivel do ADC no core.
  const float adcVoltage = analogReadMilliVolts(PORT_SENSOR) / 1000.0f;
  const float sensorVoltage = adcVoltage * RAZAO_DIV_TENSAO;
  const float pressaoKPa = (sensorVoltage / MPX_SUPPLY_V - 0.04f) / 0.09f;
  // A faixa negativa calculada nao e medida diferencial negativa validada.
  return pressaoKPa * 1000.0f;
}

