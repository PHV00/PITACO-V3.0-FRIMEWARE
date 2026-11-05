# frimeware2.5 — firmware PITACO com SoC

A pasta `frimeware2.5` conserva o nome exato solicitado. O arquivo
principal do sketch e `frimeware2.5.ino`: a especificacao Arduino
permite ponto no nome e exige que arquivo principal e pasta coincidam.

Esta e uma **copia historica** (snapshot do codigo anterior a reorganizacao). A implementacao canonica atual vive em `arduino-pitaco-mpx5010dp-unity/firmware/pitaco_2_4/`, mantendo paridade de codigo por testes.

Esta e uma **copia funcional** da versao SoC do firmware na branch
`feature/ppg-sqi-bpm-25hz-validation` (commit `2274ba6`).
Mantivemos o sketch antigo para nao afetar o middleware Python, os
testes e o fluxo USB/BLE existentes.

## Compilacao

Abra `frimeware2.5/frimeware2.5.ino` na Arduino IDE com a placa ESP32-C3
selecionada, ou execute da raiz do repositorio:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.5
```

O core ESP32 deve estar instalado. O driver SparkFun local foi copiado
integralmente para `src/vendor_sparkfun_max3010x/`, inclusive FIFO64.
Nao substitua esse driver por uma biblioteca global sem repetir os testes.

## Onde esta cada parte

| Arquivo | Responsabilidade |
| --- | --- |
| `frimeware2.5.ino` | Orquestrador setup/loop, parametros e estados |
| `pitaco_ble_ota.ino` | BLE, USB, notificacoes e OTA |
| `pitaco_commands.ino` | Comandos e/r/f/c/z |
| `pitaco_respiration.ino` | MPX5010DP, filtros e calibracao |
| `pitaco_ppg_sensor.ino` | MAX30105, FIFO64, I2C |
| `pitaco_ppg_contact_sqi.ino` | Contato optico e ciclo G1 |
| `gate_01_integrity.ino` | Estatisticas RED/IR e G1 |
| `pitaco_ppg_bpm.ino` | Detector e calculo experimental BPM |
| `pitaco_ppg_json.ino` | Serializacao JSONL |
| `src/vendor_sparkfun_max3010x/` | Driver SparkFun corrigido |

Documentacao local: [mapa SoC](docs/SOC_INO_TABS.md) e
[Gate 01](docs/GATE_01.md). A GUI, os testes de analise offline
e a ponte Unity continuam na pasta original.

## Paridade e limitacoes

O CI compila o sketch original e este novo; o teste
`arduino-pitaco-mpx5010dp-unity/tests/test_firmware25_snapshot.py`
garante que as nove abas autorais e os seis arquivos do driver
permanecam identicos aos originais. Se futuramente evoluirmos apenas
uma das pastas, precisaremos atualizar ou encerrar essa verificacao
explicitamente, evitando duas versoes divergentes sem controle.

A mudanca e **organizacional**. Os limiares, taxas PPG ~25 Hz, MPX ~20 Hz,
BPM, G1, JSONL, UUIDs e OTA nao foram alterados. A nova pasta nao
representa validacao fisiologica ou certificacao clinica. Testes de
hardware e BLE sob carga continuam pendentes.
