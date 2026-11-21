// SoC: inicializacao, ciclo de vida, leitura da FIFO e recuperacao I2C.
// PPG nao altera G1, filtros, taxas, protocolo ou prioridades do loop.

// Configura MAX30105, LEDs, FIFO e estado inicial STOPPED.
void InitMAX30105() {
  // Diagnostico temporario para o ESP32-C3 + MAX30102 (endereco 0x57).
  // Nao altera G1, FIFO, BPM, pressao ou protocolo BLE.
  Serial.printf("X,I2C_PINS,sda=%d,scl=%d\n", MAX30105_SDA, MAX30105_SCL);
  const bool i2cStarted = Wire.begin(MAX30105_SDA, MAX30105_SCL);
  Wire.setClock(I2C_SPEED_STANDARD);
  Serial.printf("X,I2C_BEGIN,%u\n", i2cStarted ? 1U : 0U);

  delay(200); // Tempo para estabilizacao da alimentacao do sensor.

  Wire.beginTransmission(0x57);
  const uint8_t ack = Wire.endTransmission();
  Serial.printf("X,I2C_ACK,%u\n", (unsigned)ack);

  if (ack == 0) {
    Wire.beginTransmission(0x57);
    Wire.write(0xFF); // PART ID
    const uint8_t registerStatus = Wire.endTransmission(false);
    Serial.printf("X,I2C_PART_REG_SELECT,%u\n", (unsigned)registerStatus);

    if (registerStatus == 0 &&
        Wire.requestFrom((uint8_t)0x57, (uint8_t)1) == 1) {
      const uint8_t partId = Wire.read();
      Serial.printf("X,PART_ID,0x%02X\n", (unsigned)partId);
    } else {
      Serial.println("X,PART_ID_READ_FAILED");
    }
  }

  const bool driverOk = max30105.begin(Wire, I2C_SPEED_STANDARD);
  Serial.printf("X,DRIVER_BEGIN,%u\n", driverOk ? 1U : 0U);
  if (!driverOk) {
    // Testa se a segunda chamada interna a Wire.begin mudou o barramento.
    Wire.beginTransmission(0x57);
    const uint8_t ackAfterDriver = Wire.endTransmission();
    Serial.printf("X,I2C_ACK_POST_DRIVER,%u\n", (unsigned)ackAfterDriver);
    Serial.println("X,MAX30105_NOT_FOUND");
    return;
  }
  // RED+IR, 100 Hz com FIFO avg 4 (~25 amostras/s), largura 411us (18bits).
  max30105.setup(0x1F, 4, 2, 100, 411, 4096);
  max30105.setPulseAmplitudeRed(0x1F);
  max30105.setPulseAmplitudeIR(0x1F);
  max30105.setPulseAmplitudeGreen(0);
  max30105.disableFIFORollover();
  // STOPPED: a conversao nao deve continuar durante espera pelo comando r.
  // Evita que a FIFO encha antes da primeira coleta (32 registros fisicos).
  max30105.shutDown();
  max30105.clearFIFO();
  ResetPpgContact();
  g1Reset();
  ppgReady = true;
  Serial.println("X,MAX30105_READY,RED_IR");
  Serial.println("X,PPG_STATE,STOPPED");
}

// Executa FIFO, contato, BPM experimental, RAW e Gate 01 sem bloquear MPX.
void PollMAX30105() {
  if (!ppgReady) return;

  // O PPG acompanha a sessao respiratoria; durante zero/OTA ele tambem para.
  const bool enabled = isSampling && isCalibrated &&
                       !isOtaUpdating && !zeroInProgress;

  if (!enabled) {
    if (ppgSampling) {
      // STOPPED: suspende as conversoes. Nao descarta dados durante a coleta;
      // uma janela parcial e intencionalmente encerrada ao comando de parada.
      max30105.shutDown();
      ppgSampling = false;
      ResetPpgContact();
      g1Reset();
      g1Ready = false;
      g1Passed = false;
      g1Reason = 1;
      heartBpm = 0;
      lastBeatMs = 0;
      Serial.println("X,PPG_STATE,STOPPED");
    }
    return;
  }

  const unsigned long now = millis();
  if (!ppgSampling) {
    // COLLECTING: preparar a FIFO ainda em shutdown. No teste de bancada,
    // zerar ovf=31 enquanto parado funcionou; enquanto ativo nao funcionou.
    max30105.clearFIFO();
    // Diagnostico do driver efetivamente linkado, emitido a cada inicio
    // de sessao. Nao altera FIFO, BPM, G1 ou o JSON de amostras.
    const uint8_t swSlots = max30105.getSoftwareBufferCapacity();
    Serial.printf("X,PPG_DRIVER,impl=vendor_safe_fifo,sw_slots=%u,sw_usable=%u\n",
                  (unsigned)swSlots,
                  (unsigned)(swSlots > 0 ? swSlots - 1 : 0));
    const uint8_t preOvf = max30105.readRegister8(0x57, 0x05);
    const uint8_t preWr = max30105.getWritePointer();
    const uint8_t preRd = max30105.getReadPointer();
    Serial.printf("X,PPG_PRESTART,ovf=%u,wr=%u,rd=%u\n",
                  (unsigned)preOvf, (unsigned)preWr, (unsigned)preRd);
    if (preOvf != 0 || preWr != 0 || preRd != 0) {
      // Falha de MAX30105 nao pode bloquear a pressao do PITACO.
      max30105.shutDown();
      ppgReady = false;
      Serial.println("X,PPG_ERROR,PRESTART_RESET_FAILED");
      return;
    }

    max30105.wakeUp();
    const uint8_t modeAwake = max30105.readRegister8(0x57, 0x09);
    Serial.printf("X,PPG_SENSOR_AWAKE,mode=%02X\n", (unsigned)modeAwake);
    if ((modeAwake & 0x80U) != 0) {
      max30105.shutDown();
      ppgReady = false;
      Serial.println("X,PPG_ERROR,WAKEUP_FAILED");
      return;
    }
    ResetPpgContact();
    g1Reset();
    ppgSampling = true;
    ppgWindowStartMs = now;
    ppgLastPollMs = now;
    ppgLastDiagMs = now;
    ppgDiagFound = 0;
    ppgDiagProcessed = 0;
    ppgBeatDetections = 0;
    g1Ready = false;
    g1Passed = false;
    g1Reason = 1;
    heartBpm = 0;
    lastBeatMs = 0;
    ++g1Window;
    Serial.println("X,PPG_STATE,COLLECTING");
  } else if ((unsigned long)(now - ppgLastPollMs) > PPG_POLL_GAP_MS) {
    // Uma chamada atrasada invalida a janela, mesmo que a FIFO tenha dados.
    g1MarkAcquisitionGap();
  }
  ppgLastPollMs = now;

  // O MAX30105 possui FIFO fisica de 32 registros. Com rollover desabilitado,
  // overflow pode deixar WR_PTR == RD_PTR e check() reportando zero.
  // Antes de qualquer descarte, tentamos consumir as amostras legiveis.
  const uint8_t ovf = max30105.readRegister8(0x57, 0x05);
  if (ovf > 0) {
    g1MarkAcquisitionGap();
    Serial.printf("X,PPG_FIFO_OVERFLOW,ovf=%u\n", (unsigned)ovf);
  }

  // A versao local da SparkFun le em blocos inteiros, ate a capacidade livre
  // do anel de 64 slots (63 utilizaveis), sem sobrescrever amostras pendentes.
  const uint16_t novos = max30105.check();
  const bool fifoReadError = max30105.takeFIFOReadError();
  const uint8_t disponiveis = max30105.available();
  ppgDiagFound += novos;
  if (fifoReadError) {
    // Uma leitura I2C truncada nao pode virar amostra nem G1 PASS.
    g1MarkAcquisitionGap();
    Serial.println("X,PPG_I2C_FIFO_READ_ERROR");
  }

  if (novos > disponiveis) {
    // O check() leu mais do que o anel interno conseguiu preservar.
    // Registra perda explicitamente para evitar falsos PASS do Gate 01.
    g1MarkAcquisitionGap();
    Serial.printf("X,PPG_SW_RING_OVERRUN,novas=%u,disponiveis=%u,sw_slots=%u\n",
                  (unsigned)novos, (unsigned)disponiveis,
                  (unsigned)max30105.getSoftwareBufferCapacity());
  }

  while (max30105.available()) {
    const uint32_t red = max30105.getFIFORed();
    const uint32_t ir = max30105.getFIFOIR();
    const unsigned long receiveMs = millis(); // leitura FIFO, nao timestamp ADC
    ++ppgSeq;

    const bool opticalPresent = UpdatePpgContact(red, ir, receiveMs);
    g1Add(red, ir);
    ProcessPpgBeat(ir, receiveMs, opticalPresent);
    PublishPpgSample(red, ir, receiveMs, opticalPresent);
    max30105.nextSample();
    ++ppgDiagProcessed;
  }

  if (ovf > 0 || fifoReadError) {
    // Overflow fisico OU transferencia I2C incompleta exigem re-sincronizacao.
    // Somente depois de tentar processar os registros acessiveis.
    // Nao limpar continuamente: desligar conversoes, resetar FIFO e
    // confirmar os registradores antes de voltar a adquirir.
    max30105.shutDown();
    max30105.clearFIFO();
    const uint8_t resetOvf = max30105.readRegister8(0x57, 0x05);
    const uint8_t resetWr = max30105.getWritePointer();
    const uint8_t resetRd = max30105.getReadPointer();
    Serial.printf(
      "X,PPG_FIFO_RESET_CHECK,antes=%u,depois=%u,wr=%u,rd=%u\n",
      (unsigned)ovf, (unsigned)resetOvf,
      (unsigned)resetWr, (unsigned)resetRd
    );

    // A perda invalida a janela atual e qualquer BPM anterior.
    g1Ready = false;
    g1Passed = false;
    heartBpm = 0.0f;
    lastBeatMs = 0;

    if (resetOvf != 0 || resetWr != 0 || resetRd != 0) {
      // Evita loop infinito de logs e preserva MPX5010DP + USB/BLE.
      ppgReady = false;
      ppgSampling = false;
      Serial.println("X,PPG_ERROR,FIFO_RESET_FAILED");
      return;
    }

    max30105.wakeUp();
    const uint8_t modeRecovered = max30105.readRegister8(0x57, 0x09);
    if ((modeRecovered & 0x80U) != 0) {
      max30105.shutDown();
      ppgReady = false;
      ppgSampling = false;
      Serial.println("X,PPG_ERROR,FIFO_WAKEUP_FAILED");
      return;
    }
    ppgLastPollMs = millis();
    Serial.println("X,PPG_FIFO_RECOVERED");
  }

#if PPG_DIAG
  if ((unsigned long)(millis() - ppgLastDiagMs) >= PPG_DIAG_MS) {
    ppgLastDiagMs = millis();
    const uint8_t wr = max30105.getWritePointer();
    const uint8_t rd = max30105.getReadPointer();
    Serial.printf(
      "X,PPG_DIAG,novas=%lu,processadas=%lu,wr=%u,rd=%u,ovf=%u,beats=%u,contact=%u\n",
      (unsigned long)ppgDiagFound, (unsigned long)ppgDiagProcessed,
      (unsigned)wr, (unsigned)rd,
      (unsigned)max30105.readRegister8(0x57, 0x05),
      (unsigned)ppgBeatDetections, ppgContactPresent ? 1U : 0U);
    ppgDiagFound = 0;
    ppgDiagProcessed = 0;
    ppgBeatDetections = 0;
  }
#endif

  PollPpgGateWindow();
}
