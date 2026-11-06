# PITACO — ESP32-C3 + MAX30105 + MPX5010DP

Este repositório contém o firmware 2.4, o middleware Python USB/BLE, os testes automatizados e o firmware legado do PITACO.

## Organização atual

```text
PITACO_ESP32/
├── frimeware2.4/                         # Firmware canônico ESP32-C3
│   ├── frimeware2.4.ino                 # setup/loop, parâmetros e interfaces
│   ├── communication/                   # BLE/USB, comandos e JSON PPG
│   ├── sensors/                         # MAX30105 + MPX5010DP
│   ├── processing/                      # BPM e controle de contato
│   ├── sqi/                             # Gate 01
│   └── src/vendor_sparkfun_max3010x/    # Driver local SparkFun FIFO64
├── arduino-pitaco-mpx5010dp-ble/         # Aplicação Python do PITACO
│   ├── ble_client_mpx5010dp.py          # Entrada GUI
│   ├── pitaco_bridge/                   # Protocolo, monitor, GUI, pneumo
│   └── pitaco_experimental/             # Aquisição e análise offline
├── arduino-pitaco-ble-legancy/           # Versão legada, sem MAX30105
├── test/                                # Testes Python e G1 C++
├── docs/                                # Fundamentos e protocolos
├── requirements.txt                     # Dependências Python
└── .github/workflows/                   # CI
```

**Nomes históricos:** a versão 2.4 usa o MAX30105 nos canais RED/IR. A pasta `frimeware2.5/` anterior foi removida por duplicação de código, mas permanece recuperável pelo histórico do Git. `arduino-pitaco-ble-legancy` conserva o nome solicitado para o legado.

## Compilar e carregar o firmware 2.4

Abra `frimeware2.4/frimeware2.4.ino` na Arduino IDE e selecione a placa ESP32-C3. Para compilar no terminal:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.4
```

As rotinas estão organizadas em subpastas por responsabilidade. **O Arduino não concatena automaticamente `.ino` de subdiretórios:** o orquestrador inclui os módulos explicitamente. O driver em `src/` é compilado recursivamente como C++ e contém correções locais da FIFO64; não substituí-lo por uma biblioteca externa sem testes.

## Executar a aplicação Python

Na raiz do repositório, em PowerShell:

```powershell
python -m pip install -r requirements.txt
python .\arduino-pitaco-mpx5010dp-ble\ble_client_mpx5010dp.py
```

A aplicação recebe dados USB ou BLE e mantém a saída numérica legada de pressão/fluxo para Unity. BPM e SpO₂ experimental são mostrados no monitor, mas a SpO₂ não é calibrada e **não deve ser usada clinicamente**.

## Verificações de regressão

```powershell
python -m unittest discover -s test -p "test_*.py" -v
python .\arduino-pitaco-mpx5010dp-ble\pitaco_experimental\pitaco24_ppg_probe.py --help
python .\arduino-pitaco-mpx5010dp-ble\pitaco_experimental\analyze_ppg_25hz.py --help
```

Teste G1 C++ em Linux:

```bash
g++ -std=c++11 -Wall -Wextra -Werror test/test_sqi_gate1.cpp -o /tmp/pitaco_g1
/tmp/pitaco_g1
```

A CI cobre host e compilação Arduino; a verificação física no ESP32-C3 continua necessária após alterações estruturais.

## Documentação

- [Arquitetura e decisões de compilação](docs/ARCHITECTURE.md)
- [Baseline, calibração e parâmetros](docs/firmware/BASELINE.md)
- [Mapa dos módulos do firmware](docs/firmware/SOC_INO_TABS.md)
- [Gate 01 / SQI](docs/firmware/GATE_01.md)
- [Validação PPG a 25 Hz](docs/firmware/PPG_VALIDATION_25HZ.md)
- [Bridge e GUI Python](docs/bridge/MIDDLEWARE_MODULAR.md)
- [USB/BLE](docs/bridge/BLE_USB.md)
- [Monitor de PPG e SpO₂ experimental](docs/bridge/PPG_GUI_MONITOR.md)
- [Relatórios e ensaios anteriores](docs/bench/README_TESTE_FIFO_PPG.md)

## Desenvolvimento e preservação de versões

Não alterar parâmetros de G1, correntes de LED, taxa de aquisição, médias móveis ou algoritmos de oximetria como efeito colateral de refatorações de pastas. Os PRs experimentais BLE compacto e Unity Combo devem ser adaptados ao layout atual em branches específicas.



Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python .\arduino-pitaco-mpx5010dp-ble\ble_client_mpx5010dp.py