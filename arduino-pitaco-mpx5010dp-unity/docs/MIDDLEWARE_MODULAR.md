# PITACO 2.4 — reorganização do middleware Python existente

**Escopo:** recortar o código preexistente e colocá-lo em arquivos por responsabilidade. Nenhum novo algoritmo, protocolo BLE, cálculo de BPM, regra G1 ou alteração no firmware.

```text
arduino-pitaco-mpx5010dp-unity/
├── ble_client_mpx5010dp.py    # MAIN: inicia interface
├── pitaco_bridge/
│   ├── gui.py                  # janela original, conexões USB/BLE, gráficos, OTA, Unity
│   ├── configuration.py        # defaults, load_config(), get_config_path()
│   ├── ports.py                # get_all_com_ports()
│   ├── pneumo.py               # calculate_flow(), flow_to_pressure(), PressureFilter
│   ├── protocol.py             # parse_pitaco_line(), BleJsonlBuffer
│   ├── monitor.py              # PpgMonitor, PpgCsvRecorder
│   └── experimental.py         # estimativas experimentais BPM / SpO2
├── pitaco24_protocol.py       # import antigo preservado
├── pitaco24_monitor.py        # import antigo preservado
├── pitaco24_experimental.py   # import antigo preservado
└── tests/                     # testes existentes
```

## Preservação da versão anterior

O código de `gui.py` é o original, menos os trechos movidos para `configuration.py`, `ports.py` e `pneumo.py`. As funções de USB, BLE, Unity, zero, OTA, gráficos e processamento de PPG não foram substituídas por novas implementações.

O módulo `pneumo.py` mantém as fórmulas e o filtro respiratório como antes. A única adaptação ao mover a variável global é: `set_flow_multiplier()` agora altera `pneumo.flow_multiplier`; `save_config()` lê o mesmo valor no módulo.

Os arquivos de compatibilidade só importam e exportam as classes/funções que já existiam; os cálculos foram movidos, não duplicados.

## Como executar

```powershell
python .\ble_client_mpx5010dp.py
python -m unittest discover -s tests -p "test_*.py" -v
```

A interface gráfica continua reunida em `gui.py` porque seus callbacks compartilham variáveis globais da aplicação original. Separar as views requer uma segunda alteração de injeção/encapsulamento de estado, a ser feita separadamente e testada.
