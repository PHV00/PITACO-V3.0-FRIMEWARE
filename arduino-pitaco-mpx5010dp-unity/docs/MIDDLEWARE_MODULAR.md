# Middleware PITACO 2.4 — arquitetura modular (USB/BLE/Pneumo/PPG)

## Objetivo

Separar a comunicacao, a interpretacao de dados e os calculos do monitor
sem modificar a logica clinica/experimental, o protocolo do ESP32-C3, o
pneumografo MPX5010DP ou os comandos originais para Unity.

```text
arduino-pitaco-mpx5010dp-unity/
├── ble_client_mpx5010dp.py       # MAIN: entrada; chama run_gui()
├── pitaco_bridge/
│   ├── __init__.py
│   ├── gui.py                     # Interface legada, graficos, conexoes e OTA
│   ├── transport.py               # PitacoMessageRouter: USB/BLE -> eventos
│   ├── protocol.py                # parse_pitaco_line / BleJsonlBuffer
│   ├── monitor.py                 # PpgMonitor, CSV, sequencia, G1, BPM FW
│   └── experimental.py            # BPM Python/SpO2 demonstrativa nao calibrada
├── pitaco24_protocol.py          # shim temporario para imports existentes
├── pitaco24_monitor.py           # shim temporario para imports existentes
├── pitaco24_experimental.py      # shim temporario para imports existentes
├── tests/
│   ├── test_pitaco24_protocol.py
│   ├── test_ppg_monitor.py
│   ├── test_ppg_experimental.py
│   └── test_pitaco_bridge_transport.py
└── docs/MIDDLEWARE_MODULAR.md
```

## Caminho dos dados

```text
ESP32-C3 / MAX30102 / MPX5010DP
          | USB Serial ou BLE GATT
          v
     gui.py (IO real)
          | linhas / fragmentos PPG
          v
   transport.PitacoMessageRouter
          |   +-- protocol.parse_pitaco_line (JSON ou Pa legado)
          |   +-- protocol.BleJsonlBuffer (reagrupa notificacoes)
          |   +-- monitor.PpgMonitor (guarda RAW, G1, contato, perdas, CSV)
          |           +-- experimental.ExperimentalPpgAnalyzer (somente PC)
          |   +-- callback da pressao -> pneumo legado
          |   +-- BPM FW validado -> COM oxi da Unity (FC,0; ate 1 Hz)
          v
  gui.py (Pneumo, PPG RED/IR, BPM FW/Python EXP, SpO2 EXP)
```

**Fronteiras e invariantes:**
- Protocolo e calculos nao importam GUI, BLE ou pyserial.
- Fragmentos BLE somente geram eventos ao completar LF; JSON invalido e contabilizado.
- PPG RAW de qualquer qualidade permanece disponivel para monitor/CSV; perdas
  nao sao preenchidas artificialmente.
- Pressao de `sample` ou linha antiga atualiza pneumografo quando permitido.
  Canal PPG BLE dedicado nao reinterpreta PPG como fluxo.
- BPM encaminhado a Unity e exclusivamente o valor FW com `bpm_valid`,
  G1 PASS e intervalo valido (35..200), limitado a uma escrita por segundo.
  0 na segunda coluna significa SpO2 indisponivel, nao saturacao medida.
- BLE reconnect limpa fragmentos pendentes; nova sessao reinicia rate-limit.
- OTA, calibracoes, comandos e pneumografia originais continuam em `gui.py`
  nesta primeira etapa da refatoracao, evitando uma mudanca generalizada.

## Como executar

Na pasta do sketch:

```powershell
python .\ble_client_mpx5010dp.py
python -m unittest discover -s tests -p "test_*.py" -v
```

A entrada historica e as opcoes da GUI sao preservadas. Para programas novos:
```python
from pitaco_bridge.protocol import parse_pitaco_line
from pitaco_bridge.monitor import PpgMonitor
from pitaco_bridge.transport import PitacoMessageRouter
```

## Responsabilidades (funcoes)

| Arquivo | Funcao/classe | Papel |
|---|---|---|
| `ble_client_mpx5010dp.py` | `run_gui()` | Inicia aplicativo |
| `gui.py` | `ble_bridge()`, `usb_read_device_loop()` | Conexao fisica e leitura |
| `gui.py` | `notification_handler()` | Canal legado BLE (pressao/echo/zero) |
| `gui.py` | `ppg_notification_handler()` | Encaminha notificacoes opticas |
| `transport.py` | `PitacoMessageRouter.process_line()` | Despacha pressao, sample e g1 |
| `transport.py` | `feed_ble_ppg()` | Remonta BLE, contabiliza frames invalidos |
| `protocol.py` | `parse_pitaco_line()` | Parse estrito e fallback Pa legado |
| `protocol.py` | `BleJsonlBuffer.feed()` | Remonta JSONL fragmentado |
| `monitor.py` | `PpgMonitor.observe()/snapshot()` | G1, contato, contadores, historicos |
| `monitor.py` | `PpgCsvRecorder` | Persistencia assinc. de sinais |
| `experimental.py` | `estimate_experimental()` | BPM por autocorrelacao, indice R/SpO2 demo |
| `gui.py` | `update_ppg_plot()` | Apenas redesenha graficos a partir do snapshot |

## Evolucao futura

A separacao de `gui.py` (ainda grande por preservar o aplicativo original)
em `pneumo_view.py`, `ppg_view.py`, `ota.py` e `settings.py` deve ser
incremental, sem criar dois donos do mesmo estado da conexao. O proximo passo
e estruturar um `ConnectionController` com ciclo de vida explicito e testes
de reconexao USB/BLE sem janelas Tk.
