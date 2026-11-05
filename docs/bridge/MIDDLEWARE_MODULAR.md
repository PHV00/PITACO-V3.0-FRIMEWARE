# PITACO 2.4 — middleware Python dividido por telas

A reorganização desta etapa move **as telas e seus callbacks já existentes**
para três arquivos, sem modificar protocolo USB/BLE, lógica da Unity,
Gate 01, detector de BPM ou cálculo experimental de SpO₂.

```text
arduino-pitaco-mpx5010dp-ble/
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

Na raiz do repositório (separada do sketch Arduino):

```powershell
python .\arduino-pitaco-mpx5010dp-ble\ble_client_mpx5010dp.py
python -m unittest discover -s test -p "test_*.py" -v
```

Verificar no Windows as duas janelas simultâneas, aferições, abertura e
fechamento sem interromper a outra, conexão BLE/USB, CSV e Unity.
Os testes automatizados checam sintaxe/contratos; não substituem o teste
físico nem a GUI real.

## Oxímetro integrado ao ESP32 — sem segunda COM

A seleção de porta virtual de oxímetro, seu estado, comandos `echox` e
thread de escrita `FC,0` foram removidos de `main_window.py`.
O MAX30105 está conectado diretamente ao ESP32 e envia RED, IR, BPM e SQI
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

O Python calcula com janela progressiva de ~3 a 8 segundos, atualizada
aproximadamente a cada 400 ms. **Contato e G1 são diagnósticos de qualidade,
não gates de cálculo**. BPM depende da periodicidade IR e SpO₂ DEMO da razão
RED/IR, de forma independente. DC/AC baixos, movimento e baixa coerência
são alertas; condições matemáticas impossíveis continuam produzindo `--`.
As lacunas não eliminam candidatos anteriores do histórico. A SpO₂ não foi
calibrada, não tem uso clínico e **não é enviada à Unity**.

A janela `Monitor Cardíaco / SpO₂` dispõe de **dois cartões no canto superior
direito**: um com BPM atual do ESP32 e do Python experimental, outro com
SpO₂ experimental instantânea. Todos mostram `--` quando indisponíveis.
O firmware, o cálculo de BPM embarcado, os gráficos respiratórios, BLE/USB e
CSV RAW permanecem inalterados por esta alteração.

### Históricos e qualidade separados

O painel traz status de qualidade distinto dos cartões BPM e SpO₂. O RAW
passou de aproximadamente 12 para **30 segundos visíveis**, usando buffer
de 850 pontos. O contador `Reinícios seq` permite detectar reinicialização
do firmware. Os históricos BPM/SpO₂ não são apagados em perdas transitórias
de contato, gaps ou reprovação G1; somente as leituras **atuais** podem
ficar indisponíveis. Os dados RAW continuam disponíveis para exportação CSV.

### Correção contra falsas SpO₂ com dedo ausente

A função de cálculo experimental permanece independente do G1 e gera
candidatos `spo2_candidate` / `bpm_candidate` para comparação offline.
A apresentação dos resultados atuais `spo2` / `bpm` exige contato
óptico confirmado (`sqi.contact=true`) e nível RED/IR suficiente;
a SpO₂ também requer AC e coerência dos canais suficientes para exibição.
Sem contato a interface mostra `--` e mantém o histórico anterior.
O retorno do dedo reinicia somente a janela móvel; o firmware não é
alterado, e a SpO₂ demonstrativa continua não calibrada e não clínica.

### Quatro indicadores superiores — médias móveis de 60 s

O painel `oxy_and_cardio_view.py` mantém BPM atual (ESP32/Python) e SpO₂
experimental atual. Adiciona, ao lado, BPM médio (ESP32/Python separados)
e SpO₂ média experimental, em um grid 2x2. Ambos os indicadores médios
usam o modelo compartilhado `PpgMonitor.snapshot()["mean60"]`.

O `pitaco_bridge/monitor.py` calcula a média por segundo dos valores
válidos exibíveis nos últimos 60 segundos, com cobertura e estado
parcial/completa. O firmware requer retenção independente para a média
(`bpm_mean_history`, 1800 pontos) já que a vista RAW guarda apenas
aproximadamente 30 s. Os dois históricos Python já têm retenção suficiente.
G1 permanece diagnóstico no Python e critério de validade no ESP32.
Sem contato, desconexão, perda de amostras ou nova colocação de dedo,
a média corrente não reutiliza a sessão anterior.
