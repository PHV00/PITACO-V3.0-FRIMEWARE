# Firmware PITACO 2.4 — MAX30105 + MPX5010DP

Sketch canônico: **`frimeware2.4.ino`**. Compilar pela raiz com:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.4
```

- `communication/`: BLE/OTA, comandos, telemetria JSON.
- `sensors/`: pressão MPX5010DP e PPG MAX30105.
- `processing/`: contato óptico, periodicidade e BPM.
- `sqi/`: Gate 01 com estatísticas e códigos de falha.
- `src/vendor_sparkfun_max3010x/`: biblioteca C++ local SparkFun, incluindo driver FIFO64 e licença.

**Importante:** como as rotinas autorais estão em subdiretórios, o orquestrador as inclui explicitamente. Não abrir os módulos individuais como sketches. A aquisição usa RED+IR, não o LED verde, e SpO₂ exibida no Python continua experimental e não calibrada. A organização não muda a fiação, os limiares nem o protocolo USB/BLE.
