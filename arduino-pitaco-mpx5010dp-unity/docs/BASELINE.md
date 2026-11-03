# PITACO 2.4 — baseline preservado

## Arquitetura mínima e origem

- **Firmware orquestrador:** arduino-pitaco-mpx5010dp-unity.ino. Preserva o MPX5010DP, o ADC de pressão, o filtro, a calibração, os comandos de operação, a saída USB numérica, o GATT BLE original e a OTA. Acrescenta MAX30105, RED/IR, detector de contato, BPM SparkFun experimental e JSONL.
- **Gate 01:** gate_01_integrity.ino. Acumula estatísticas RED/IR sem transformar ou descartar o sinal. Ver [GATE_01.md](GATE_01.md).
- **Ponte PC/Unity:** ble_client_mpx5010dp.py (GUI adaptada); pitaco24_protocol.py (parser e remontagem de notificações); pitaco24_ppg_probe.py (diagnóstico opcional, não faz parte do firmware).
- **Legado preservado:** arquivos na pasta arduino-pitaco-ble/, características antigas de pressão, comandos e OTA. Não converter pressão calibrada em fluxo clínico sem validação.
- **Testes mantidos:** tests/ e workflow .github/workflows/pitaco24-g1.yml. São proteção contra regressões, não lixo de bancada.

## Responsabilidade de cada função do orquestrador

| Função ou callback | O que faz |
| --- | --- |
| setup | Inicializa Serial, ADC, BLE (pressão, OTA e PPG), advertising e MAX30105 |
| loop | Processa comandos USB, FIFO do PPG, zero e pressão MPX na cadência existente |
| MyServerCallbacks.onConnect/onDisconnect | Marca conexão BLE e reinicia advertising quando desconecta |
| MyCallbacks.onWrite | Recebe comando escrito na characteristic BLE de pressão |
| OtaControlCallbacks.onWrite | Inicia, finaliza/reinicia ou aborta OTA (0x01/0x02/0x03) |
| OtaDataCallbacks.onWrite | Grava blocos OTA com Update.write durante atualização |
| ListenCommand | Comandos originais: e/echop e parada; r/início; f/parada; c/calibração curta; z/zero 10 s |
| SendStatus | Envia status ao USB e, conectado, à characteristic antiga |
| voutToPa | ADC do MPX, divisor resistivo e conversão experimental para Pa |
| ReadRawPressurePa | Filtro média móvel/EMA antes de offset e deadband |
| Calibrate | Offset inicial provisório 100 Pa ou referência lida por comando c |
| ResetPressureFilter | Recomeça o estado do filtro após referência nova |
| StartTenSecondZero | Inicia amostragem da referência durante 10 s |
| PollTenSecondZero | Amostra sem filtro a cada 50 ms e atualiza offset com amostras suficientes |
| ResetPpgContact | Zera confirmação de contato óptico |
| InitMAX30105 | Configura I2C, LED RED/IR e FIFO; mantém sensor parado antes de r |
| PollMAX30105 | Estados STOPPED/COLLECTING, FIFO, contato, BPM, publicação RAW, avaliação G1 e recuperação de erros |
| SendPpgJson | Envia JSONL completo por USB e até 20 bytes por notificação BLE |
| SendG1Json | Monta e transmite evento periódico da janela G1 |

Os dois arquivos .ino continuam sendo o firmware; os documentos não introduzem bibliotecas, camadas ou processamento redundantes.

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

- Testes Python: python -m unittest discover -s tests -p test_*.py
- Gate C++: g++ -std=c++11 -Wall -Wextra -Werror tests/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1
- ESP32-C3: arduino-cli compile --fqbn esp32:esp32:esp32c3 arduino-pitaco-mpx5010dp-unity
- Revisar CI do pull request e ensaiar USB/BLE em hardware, especialmente throughput BLE sob carga.

Este commit altera apenas documentação, comentários no código e regras de ignore; nenhuma função, parâmetro, limite, mensagem ou comportamento runtime foi alterado.
