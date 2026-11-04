# PITACO 2.4 — middleware Python dividido por telas

A reorganização desta etapa move **as telas e seus callbacks já existentes**
para três arquivos, sem modificar protocolo USB/BLE, lógica da Unity,
Gate 01, detector de BPM ou cálculo experimental de SpO₂.

```text
arduino-pitaco-mpx5010dp-unity/
├── ble_client_mpx5010dp.py     # Entrada original (não mudou)
└── pitaco_bridge/
    ├── gui/
    │   ├── __init__.py         # Reexporta run_gui()
    │   ├── main_window.py      # Janela principal, botões, USB/BLE, OTA e Unity
    │   ├── pneumo_view.py      # Janela respiratória, gráfico e aferições
    │   └── oxy_and_cardio_view.py      # Janela óptica, RED/IR, BPM, SpO₂ demo e CSV
    ├── configuration.py
    ├── ports.py
    ├── pneumo.py
    ├── protocol.py
    ├── monitor.py
    └── experimental.py
```

## Divisão das funções originais

| Módulo | Responsabilidades existentes |
|---|---|
| `main_window.py` | criar a janela principal; botões de conexão, comandos, configuração e OTA; conexão BLE/USB compartilhada; ponte COM e Unity |
| `pneumo_view.py` | janela respiratória; exibição de fluxo/pressão; relatório e aferições de pico, taxa e tempo inspiratório/expiratório |
| `oxy_and_cardio_view.py` | janela PPG; curvas RED/IR, BPM firmware/Python e SpO₂ demonstrativa; indicadores G1 e botão de CSV |
| `protocol.py` | ler mensagens PPG JSONL e recompor fragmentos BLE; inalterado |
| `monitor.py` | estado, histórico, contadores de perdas e gravador CSV; inalterado |
| `experimental.py` | BPM experimental e relação RED/IR; inalterado |
| `pneumo.py` | modelo e filtro de fluxo; inalterado |

### Um único estado de aplicação

Os botões e o controle de aquisição continuam em `main_window.py`.
As duas views são criadas por `create_pneumo_view(app)` e
`create_oxy_and_cardio_view(app)`, recebendo o módulo principal como referência
aos dados e ao estado compartilhados. Assim, não duplicam as conexões
BLE/USB ou as filas. A leitura de flags (`is_plotting`,
`is_ppg_plotting`, `running`) e métricas respiratórias é dinâmica;
nenhum valor é copiado para outra instância de sessão.

`main_window.py` mantém referências aos widgets necessários para
abrir e fechar janelas e encerrar uma gravação CSV. Os demais
elementos visuais ficam encapsulados nas próprias views. Esta é uma
divisão de apresentação e localização das funções; os cálculos continuam
nos módulos que já existiam.

## Execução e validação

Na pasta do sketch, como anteriormente:

```powershell
python .\ble_client_mpx5010dp.py
python -m unittest discover -s tests -p "test_*.py" -v
```

Verificar no Windows as duas janelas simultâneas, aferições, abertura e
fechamento sem interromper a outra, conexão BLE/USB, CSV e Unity.
Os testes automatizados checam sintaxe/contratos; não substituem o teste
físico nem a GUI real.

## Oxímetro integrado ao ESP32 — sem segunda COM

A seleção de porta virtual de oxímetro, seu estado, comandos `echox` e
thread de escrita `FC,0` foram removidos de `main_window.py`.
O MAX30102 está conectado diretamente ao ESP32 e envia RED, IR, BPM e SQI
no JSON PPG recebido pelo USB ou BLE existentes. Não houve alteração no
firmware, parser, qualidade do sinal ou cálculo de BPM/SpO₂. A porta virtual
do **jogo respiratório** permanece para pressão/fluxo e comandos do PITACO;
ela não passa automaticamente a transportar BPM/SpO₂ para a Unity.

## Atualização — monitor cardíaco e SpO₂ automáticos (04/11/2026)

O analisador experimental de `pitaco_bridge/experimental.py` agora é sempre
executado durante a aquisição RED/IR. O `PpgMonitor.observe()` dispara o
processamento sem depender de abertura do gráfico; `oxy_and_cardio_view.py`
mostra as curvas BPM Python e SpO₂ experimental diretamente. A antiga checkbox
foi removida. O campo `experimental.enabled=true` permanece no snapshot por
compatibilidade de leitura, mas não existe controle para desativá-lo.

As estimativas continuam condicionadas a contato, G1 e aproximadamente 8 s de
sinal contínuo. Na ausência de condições adequadas aparecem `--` e lacunas;
a SpO₂ não foi calibrada, não tem uso clínico e **não é enviada à Unity**.
O firmware, o cálculo de BPM embarcado, os gráficos respiratórios, BLE/USB e
CSV RAW permanecem inalterados por esta alteração.
