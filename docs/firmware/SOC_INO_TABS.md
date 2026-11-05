# PITACO 2.4 — Separacao de responsabilidades (SoC) em abas `.ino`

**Sketch atual:** `frimeware2.4/`, com um único orquestrador `.ino` na raiz e oito módulos `.ino` em `communication/`, `processing/`, `sensors/` e `sqi/`.

**Escopo:** refatoracao **organizacional**, sem modificar algoritmos, calibracao,
G1, BPM, FIFO, comandos, JSON, UUIDs ou taxas. O `setup()` e o `loop()`
continuam no sketch principal. Os modulos sao apenas abas do **mesmo** firmware;
nao ha Facade, Pipeline novo nem Dependency Injection.

## Mapa para encontrar e modificar o codigo

| Onde procurar | Arquivo | O que contem |
| --- | --- | --- |
| Entrada e coordenacao | `frimeware2.4.ino` | includes, parametros, estados compartilhados, prototipos, `setup()`, `loop()` |
| Comandos da sessao | `communication/pitaco_commands.ino` | `ListenCommand`: e/echop, r, f, c, z |
| BLE/USB e atualizacao | `communication/pitaco_ble_ota.ino` | callbacks, `InitBleCommunication`, `SendStatus`, `SendPpgJson`, OTA |
| Pressao respiratoria | `sensors/pitaco_respiration.ino` | `PollPressureSampling`, leitura MPX, EMA/media movel, calibracao, zero |
| Aquisição PPG | `sensors/pitaco_ppg_sensor.ino` | `InitMAX30105`, `PollMAX30105`, FIFO64, integridade I2C, estados STOPPED/COLLECTING |
| Contato e janela G1 | `processing/pitaco_ppg_contact_sqi.ino` | `ResetPpgContact`, `UpdatePpgContact`, `PollPpgGateWindow` |
| Matematica G1 | `sqi/gate_01_integrity.ino` | `g1Reset`, `g1Add`, `g1Evaluate`, thresholds (incl. 500 ADC) |
| Frequencia cardiaca | `processing/pitaco_ppg_bpm.ino` | `ProcessPpgBeat`, `IsPpgBpmValid`; chama SparkFun `checkForBeat(IR >> 3)` |
| Formato do PPG | `communication/pitaco_ppg_json.ino` | `PublishPpgSample`, `SendG1Json`, estrutura JSONL |

Exemplos: para achar **`60000 / delta`**, abrir
`pitaco_ppg_bpm.ino`. Para alterar a faixa de aceitacao RED, buscar
`G1_MIN_RANGE` em `sqi/gate_01_integrity.ino` (**nao modificar sem experimento**).
Para acompanhar overflow FIFO, abrir `sensors/pitaco_ppg_sensor.ino`.
Para alterar os UUIDs, procurar no cabeçalho do sketch principal; os
callbacks e comandos de notificacao ficam em `pitaco_ble_ota.ino`.

## Sequencia de execucao mantida

```text
setup()
 ├─ Serial/ADC
 ├─ InitBleCommunication()        [BLE e OTA originais]
 └─ InitMAX30105()                 [PPG desligado ao iniciar]

loop()
 ├─ Serial e ListenCommand()      [handshake echop]
 ├─ PollMAX30105()                 [FIFO SEM interromper pressao]
 │   ├─ UpdatePpgContact()        [redefine G1 ao mudar contato]
 │   ├─ g1Add()                    [RAW RED/IR, sem filtro]
 │   ├─ ProcessPpgBeat()          [checkForBeat da SparkFun]
 │   ├─ PublishPpgSample()        [JSONL via USB/BLE]
 │   ├─ max30105.nextSample()
 │   └─ PollPpgGateWindow()       [a cada ~5 s]
 ├─ se zeroInProgress:
 │   └─ PollTenSecondZero() + yield() + return
 ├─ PollPressureSampling()        [20 Hz, calibração e deadband]
 └─ yield()
```

A ordem das chamadas foi preservada, inclusive a prioridade de atendimento
da FIFO durante a calibracao de zero. O PPG fica suspenso durante
zero/OTA, mas **continua adquirindo RAW sem dedo** quando a coleta esta
ativa; a ausencia de contato invalida BPM e G1 efetivos.

## Por que SoC em abas `.ino` e viavel

O Arduino concatena automaticamente apenas os `.ino` da raiz de um sketch. **Como os módulos desta versão ficam em subpastas**, o orquestrador `frimeware2.4.ino` os inclui com `#include` explícitos e em ordem documentada, preservando a unidade de tradução original. Eles compartilham estados globais; protótipos de funções comuns permanecem no orquestrador. Não compilar os arquivos das subpastas como sketches independentes.

**Limitacoes**: (1) nao existe encapsulamento real de dados, portanto
qualquer aba pode modificar estados globais; (2) o Arduino pode autogerar
prototipos e depende de regras de preprocessamento, por isso evitamos tipos
complexos no limite entre abas; (3) funcoes curtas entre arquivos podem
ficar dificeis de rastrear sem este mapa; (4) o projeto continua sendo um
monolito Arduino de compilacao unica, e testes unitarios C++ puros para BPM
ainda exigiriam desacoplar hardware futuramente.

### Por que nao converter a SparkFun para `.ino`?

A pasta `frimeware2.4/src/vendor_sparkfun_max3010x/` contem o **driver de terceiros**
`MAX30105.h/.cpp` e `heartRate.h/.cpp`. Esses arquivos sao compilados
como biblioteca C++ do sketch e possuem estruturas e definicoes que
nao devem ser simplesmente renomeadas para `.ino`. A versao local inclui
a correção FIFO64 previamente validada. Converter a biblioteca arriscaria
erros de declaracao e multiplas definicoes, alteraria a proveniencia da
implementacao e poderia introduzir regressoes na leitura FIFO. **Por
isso somente o codigo autoral do firmware foi reorganizado em `.ino`**;
o driver C++ local e mantido intacto.

## Escopo deliberadamente nao alterado

- Taxas: MPX ~20 Hz, MAX30105 100 Hz com média FIFO 4 (~25 pares/s).
- G1: 5 s, limite de 500 ADC, marcacao de gap, contato e validacao.
- Detector: FIR da SparkFun, `IR >> 3`, 35..200 BPM, suavizacao 0.7/0.3.
- FIFO: 64 posicoes no driver, recuperação e telemetria de erro I2C.
- Serial: pressao legada, USB JSONL, fragmentacao BLE de 20 bytes, OTA.
- Nenhum contrato Unity/ML-Agents, Python ou algoritmo de SpO2 foi alterado.

## Validacao requerida antes de promover

1. `g++ -std=c++11 -Wall -Wextra -Werror test/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1`;
2. `python3 -m unittest discover -s test -p 'test_*.py'`, incluindo
   `test_ppg_lifecycle_contract.py` adaptado para abas;
3. `arduino-cli compile --fqbn esp32:esp32:esp32c3 firmware/pitaco_2_4`;
4. Com a placa e sensor: comparar log antigo/novo, mensagens, seq, G1,
   BPM, FIFO64 e comandos e/r/f/c/z, zero de 10 s, OTA e BLE.

Os tres primeiros testes sao automatizados no PR. O quarto **exige
ensaio real**; compilar nao demonstra equivalencia de temporizacao BLE
nem o comportamento eletro-optico em hardware.

## Padrao para adicionar uma funcao

Antes de programar, responder: **"Qual dado ela recebe, que resultado
produz e qual sensor/etapa realmente possui essa responsabilidade?"**
Adicionar a funcao na aba de seu dominio, reutilizar as variaveis
compartilhadas apenas quando necessario, atualizar este mapa e
adicionar teste de regressao. Evitar introduzir outras abstracoes
ate haver uma necessidade demonstravel.
