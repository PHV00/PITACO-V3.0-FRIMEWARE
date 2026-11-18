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


## Integracao experimental G1 epoch (branch `test/ppg-g1-contact-epoch`)

O protocolo acrescenta `sqi.epoch` (inteiro de 0 a 65535) aos JSON
`type=sample` e `type=g1`; os campos anteriores continuam presentes.
`epoch` representa **identidade da sessao de qualidade**, nao qualidade
aprovada nem valor clinico. O contador e incrementado somente quando
a sessao G1 antiga fica invalida: inicio/fim da coleta, perda/retorno
**confirmados** do contato (3 amostras consecutivas) ou recuperacao
de FIFO. Janelas G1 de 5 s normais nao mudam o contador.

Um contato falso por apenas 1-2 amostras continua com `contact=false`
nesses frames e nao incrementa epoch, mas tambem **nao autoriza**
PPG instantaneo. Se o firmware indicar `reason=1`, a Unity
com epoch correspondente **suspende a publicacao** ate o proximo G1,
sem reaproveitar a aprovacao anterior. Epoch alterado obriga reset.
Firmware sem epoch aciona fallback conservador na Unity.

A recuperacao de FIFO agora inicia uma nova janela G1 e zera seu
acumulador, impedindo misturar leituras antigas/novas. Thresholds G1
(`range >= 500`, minimo 50 samples, etc.), fiação, hardware e
taxa efetiva ~25 Hz **nao foram alterados**.

### Como testar (firmware e Unity)

```bash
git fetch origin
git switch test/ppg-g1-contact-epoch
git pull --ff-only origin test/ppg-g1-contact-epoch
arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.4
```

Gravar via Arduino IDE ou `arduino-cli upload` com placa/porta
conferidas antes de iniciar o teste Unity. A branch Unity correspondente
e `test/unity-ppg-queue-throughput-probe`.

Observar `X,PPG_G1_EPOCH,epoch=...,reason=...`, o campo
`sqi.epoch` nos JSON, `G1_EPOCH_CHANGED`, `G1_REASON_WAIT`
e a ausencia de publicacao com G1 nao aprovado.

**Codigo ainda nao compilado nem validado em hardware neste ambiente.**
Nao usar SpO2 DEMO em alertas clinicos.
