# Arquitetura do repositório PITACO 2.4

## Contexto

O PITACO integra MPX5010DP para respiração e MAX30105 para PPG de dedo, sob ESP32-C3, e envia telemetria USB/BLE para um middleware Python. A interface Python acompanha pressão, RED/IR, Gate 01, BPM do firmware, BPM Python e SpO₂ demonstrativa.

## Responsabilidades

| Pasta | Responsabilidade | Compilação / execução |
| --- | --- | --- |
| `frimeware2.4/` | Firmware autoral, aquisição e SQI | `arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.4` |
| `frimeware2.4/src/vendor_sparkfun_max3010x/` | Driver SparkFun local com FIFO64 | Compilado como C++ recursivo pelo Arduino |
| `arduino-pitaco-mpx5010dp-ble/pitaco_bridge/` | Protocolo USB/BLE, monitor, GUI, fluxo | Python |
| `arduino-pitaco-mpx5010dp-ble/pitaco_experimental/` | Coleta e análise offline | Python |
| `arduino-pitaco-ble-legancy/` | Versão histórica de BLE/pressão | Não é o alvo principal do ESP32-C3 |
| `test/` | Contratos de firmware e testes de bridge, Python e Gate 01 C++ | GitHub Actions |
| `docs/` | Fundamentação, arquitetura e roteiros | Leitura humana |

## Por que os módulos autorais continuam `.ino`?

A organização `communication/`, `sensors/`, `processing/`, `sqi/` reproduz o commit de separação por responsabilidades sem reescrever algoritmos validados. O Arduino só concatena arquivos `.ino` na raiz do sketch, portanto `frimeware2.4.ino` inclui cada módulo na ordem apropriada. O CI compila o sketch completo e os testes inspecionam cada inclusão.

A abordagem usa inclusão textual: os módulos compartilham estado global e ainda **não** são C++ independente. Uma migração para `.h/.cpp` com encapsulamento deve ser avaliada em PR distinto.

## Por que existe `src/`?

`src/vendor_sparkfun_max3010x/` contém fontes e headers da biblioteca SparkFun mantida localmente. É parte necessária da compilação e inclui alterações de proteção da FIFO64. A licença é preservada. Não manter cópias paralelas em `lib/` ou em outro firmware ativo.

## Testes e riscos de integração

Os testes ficam em `test/` na raiz e encontram ambos: firmware canônico e pacote Python. A CI verifica os imports e compila o ESP32-C3. A UI real, BLE físico, OTA, COM virtual e Unity precisam de verificação adicional em hardware Windows quando houver alterações relevantes.

Os cálculos experimentais não estão calibrados para uso médico. G1 PASS não certifica a validade clínica do PPG.
