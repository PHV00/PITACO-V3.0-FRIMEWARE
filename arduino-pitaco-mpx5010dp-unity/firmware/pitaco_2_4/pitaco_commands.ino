// SoC: comandos de sessao do PITACO; contrato e/r/f/c/z inalterado.

// Contrato original: e=echop, r=iniciar, f=parar, c=calibrar, z=zero 10s.
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
