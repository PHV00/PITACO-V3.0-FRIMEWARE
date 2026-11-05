# PITACO 2.4 — baseline preservado

## Arquitetura vigente — SoC em abas `.ino`

**Sketch canônico na raiz do repositório:** `frimeware2.4/frimeware2.4.ino`. Os oito módulos `.ino` ficam em subpastas temáticas e são incluídos explicitamente pelo orquestrador.

O firmware autoral foi organizado por **Separation of Concerns**: um orquestrador principal e módulos de PPG, respiração, BLE/OTA, comandos, BPM, contato/SQI e JSON. Os `.ino` das subpastas não são descobertos automaticamente pelo Arduino: o arquivo principal contém `#include` explícito para cada um, na ordem do sketch validado. Esses módulos ainda compartilham a mesma unidade C++ e **não são bibliotecas independentes**.

**Mapa de responsabilidades e limitacoes:** [SOC_INO_TABS.md](SOC_INO_TABS.md).
**G1 e parametros:** [GATE_01.md](GATE_01.md).
**USB/BLE:** [BLE_USB.md](../bridge/BLE_USB.md).

| Arquivo | Responsabilidade |
| --- | --- |
| `frimeware2.4/frimeware2.4.ino` | `setup`, `loop`, estado compartilhado e constantes |
| `frimeware2.4/communication/pitaco_commands.ino` | `ListenCommand`, comandos e/r/f/c/z |
| `frimeware2.4/communication/pitaco_ble_ota.ino` | `InitBleCommunication`, callbacks GATT/OTA e transmissao USB/BLE |
| `frimeware2.4/sensors/pitaco_respiration.ino` | `PollPressureSampling`, ADC MPX5010DP, filtros, zero/calibracao |
| `frimeware2.4/sensors/pitaco_ppg_sensor.ino` | `InitMAX30105`, `PollMAX30105`, FIFO64, erros e I2C |
| `frimeware2.4/processing/pitaco_ppg_contact_sqi.ino` | Contato optico e fechamento da janela G1 |
| `frimeware2.4/sqi/gate_01_integrity.ino` | Estatisticas e razoes de falha G1 |
| `frimeware2.4/processing/pitaco_ppg_bpm.ino` | `checkForBeat`, RR e BPM experimental |
| `frimeware2.4/communication/pitaco_ppg_json.ino` | JSONL dos pares RED/IR e eventos G1 |

O driver SparkFun **vendorizado** `frimeware2.4/src/vendor_sparkfun_max3010x/*.h/.cpp`
nao foi alterado nem renomeado; continua necessario para FIFO64 e BPM.
A interface Python reside em `arduino-pitaco-mpx5010dp-ble/pitaco_bridge/gui/`, e nao exige segunda
COM virtual para o oximetro. Codigo de pesquisa offline em
`arduino-pitaco-mpx5010dp-ble/pitaco_bridge/ppg_validation_25hz.py` tambem permanece independente do
sketch ESP32.

## Configuração vigente — não modificar sem novo ensaio

- MPX: GPIO0; R1=2170 e R2=1500; Vs=5 V; ZERO_REFERENCE_PA=100 (provisório); deadband=15 Pa; MOVING_AVERAGE=true; SAMPLESIZE=5; EMA_ALPHA=0.35.
- PPG: MAX30105 via biblioteca SparkFun MAX3010x; SDA GPIO4, SCL GPIO5; setup(0x1F,4,2,100,411,4096): RED+IR, 100 Hz com média FIFO 4 (~25 pares/s), largura 411 us, ADC 18 bits.
- Gate: janelas de 5000 ms; atraso de polling de 180 ms sinaliza gap; contato óptico provisório com três amostras consecutivas e nível mínimo de 5000 em cada canal.
- Diagnóstico PPG_DIAG=true produz telemetria USB a cada 2 s; não é requisito do algoritmo de SQI.
- BPM experimental baseado em checkForBeat(IR deslocado de 3 bits), com suavização e bloqueio por contato e G1; **não há cálculo de SpO2**.

**Interpretação:** zero gaps de sequência observados nos ensaios USB não prova ausência de perdas pelo BLE. G1 PASS não atesta PPG fisiologicamente apto nem BPM/SpO2 clínicos. O MPX mede pressão relativa experimental; o fluxo exibido na GUI depende de modelo não validado.

## Limpeza local segura

Arquivos .csv dos ensaios, ambientes .venv e caches Python são locais; um .gitignore impede que sejam adicionados por acidente, **mas não os apaga**. Antes de remover capturas, fazer cópia caso sejam dados de pesquisa.

No PowerShell, dentro de arduino-pitaco-mpx5010dp-unity, revisar com:
- git status --short
- Get-ChildItem -Filter *.csv

Depois de salvar cópias, remover apenas capturas locais conhecidas com:
- Remove-Item .\pitaco24_capture.csv, .\ppg_contato_60s.csv, .\ppg_contato_v2.csv -ErrorAction SilentlyContinue

**Não usar git clean -fdx**, pois apagaria também dados locais, e não excluir .venv automaticamente porque ela contém o ambiente Python do desenvolvedor. Se gate_01_integrity.ino constar como modificado, usar git diff para revisar antes de restaurar ou descartar: essa edição local não é tocada pelo presente commit.

## Verificações do baseline

- Testes Python: python -m unittest discover -s test -p test_*.py
- Gate C++: g++ -std=c++11 -Wall -Wextra -Werror test/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1
- ESP32-C3: arduino-cli compile --fqbn esp32:esp32:esp32c3 firmware/pitaco_2_4
- Revisar CI do pull request e ensaiar USB/BLE em hardware, especialmente throughput BLE sob carga.

Esta refatoração muda a organização física das funções entre abas .ino. Os algoritmos, constantes e contratos permanecem previstos como invariantes; a equivalência operacional precisa ser confirmada em hardware após o CI.
