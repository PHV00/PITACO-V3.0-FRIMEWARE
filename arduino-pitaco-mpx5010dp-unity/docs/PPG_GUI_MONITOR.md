# PITACO 2.4 — middleware Python para testar PPG e Gate 01

## Objetivo

Usar o aplicativo ble_client_mpx5010dp.py (CustomTkinter + Matplotlib)
como **testador principal**, aproveitando a GUI original de pressão e fluxo.
Acrescentamos **visualização dos dados realmente recebidos no PC**: curvas
RED/IR RAW, estado de contato, G1, BPM, taxa e perdas de sequência.

Esta branch **não altera firmware, UUIDs, comandos, valores G1/BPM,
JSONL ou formato BLE**. Utiliza a characteristic PPG JSON já existente.
A PR #4 que experimenta transmissão binária permanece separada.

## Fluxo de dados

    MAX30102 + MPX5010DP -> ESP32-C3
      ├── USB: linhas numericas de pressao + JSONL sample/g1
      └── BLE:
          ├── characteristic pressao/comandos 3bcdff27...9266
          └── characteristic PPG JSONL 3bcdff2a...9266
                    │
                    ▼
        ble_client_mpx5010dp.py
          ├── parser pitaco24_protocol.py (reutilizado)
          ├── pitaco24_monitor.PpgMonitor (NOVO)
          │    ├── historico RED/IR limitado, sem filtrar
          │    ├── contadores de seq, duplicados, G1 e JSON invalido
          │    ├── gravador CSV com thread dedicada
          │    └── snapshots para graficos/indicadores da GUI
          ├── grafico original de pressao/fluxo (preservado)
          ├── grafico adicional RED/IR (NOVO)
          ├── COM virtual pressao -> Unity (preservada)
          └── COM virtual oximetro -> Unity (preservada)

## Responsabilidades

- parse_pitaco_line: valida a mensagem original.
- BleJsonlBuffer: remonta fragmentos BLE em linhas completas.
- PpgMonitor.observe: contabiliza dados recebidos, inclusive os rejeitados
  por Gate 01 e as amostras com contato ausente; não melhora o sinal.
- PpgMonitor.snapshot: oferece estado completo à thread principal do Tk.
- note_ble_fragment: conta notificações PPG, não perda de fragmento individual.
- note_invalid_json: registra linhas completas que não foram decodificadas.
- PpgCsvRecorder: escrita desacoplada do callback por fila limitada.
- update_plot: desenha fluxo e curvas ópticas com indicadores G1/contato/BPM.
- process_pitaco_line: segue fazendo o encaminhamento original para o jogo.

## Como interpretar o testador

| Métrica | Significado |
| --- | --- |
| Taxa Hz | amostras recebidas no PC na janela móvel ~10 s |
| Recebidas | frames sample aceitos pelo parser |
| Perdas seq | saltos no seq uint16; o gráfico interrompe a curva e não inventa dados |
| Duplicadas | repetição de seq; wrap 65535→0 não é erro |
| JSON inválido | linhas BLE completas que não passaram pelo parser |
| Contato | detecção experimental do firmware, não saturação de oxigênio |
| G1 | estado efetivo atual e contagem de janelas G1 |
| BPM | só se bpm_valid, sem alegar precisão clínica |
| Pressão | quantidade de linhas legadas recebidas |
| CSV descartadas | perda na fila de gravação do PC, distinta da perda BLE |

## Ensaio Windows: BLE e USB sem trocar firmware

1. Atualizar a branch do middleware e executar o aplicativo Python com
   dependências atuais no Windows. O ESP32 pode manter o firmware anterior.
2. Selecionar **Bluetooth** ou **Cabo USB**. Para o teste isolado, definir
   portas virtuais do jogo como **Somente monitor**.
3. Clicar **Conectar**, depois **Abrir Gráfico**. Esse botão continua
   enviando o comando original r para iniciar a aquisição.
4. Observar os gráficos de fluxo, RED e IR, o Gate 01, contato e BPM.
5. Clicar **Gravar CSV PPG** e escolher destino fora do repositório.
   Registra amostras RAW mesmo com G1 False ou contato ausente,
   eventos G1 e linhas de pressão.
6. Coletar 60 s com dedo parado, depois movimentos e retirada/reposição
   do dedo. Registrar taxa de PPG, gaps, duplicadas, linhas inválidas,
   janelas G1 e continuidade da pressão.
7. Encerrar gravação no mesmo botão ou desconectar. O middleware
   fecha o CSV antes de encerrar a sessão.
8. Fazer ensaio USB equivalente e comparar. Evitar dois programas abrindo
   a mesma COM física. Só depois validar GUI com Unity.

O CSV usa os campos:
type,transport,rx_s,seq,window,t_ms,red,ir,bpm,bpm_valid,pressure_pa,g1,reason,samples,contact

rx_s é o instante monotônico relativo ao início da gravação no PC;
t_ms vem do ESP32. pressure_pa embutida no sample é a última pressão
conhecida no firmware, **não uma leitura simultânea** ao PPG.
Para comparação de integridade, exigir zero gap de seq, zero linha inválida
e zero perda na fila CSV; dados sem esse requisito não provam perda zero.

## Limitações e critérios

- A GUI não valida qualidade clínica do sinal, BPM nem SpO2.
- O contrato Unity anterior permanece: COM virtual para pressão, COM
  virtual do oxímetro opcional para BPM qualificado e sentinela de
  SpO2 indisponível. Não interpretar sentinela 0 como SpO2 real.
- A taxa recebida mostra comportamento combinado da placa, rádio,
  Windows e GUI. Para distinguir problema FIFO de BLE,
  confrontar com telemetria USB X,PPG_DIAG e seus contadores.
- Testes de regressão: python -m unittest discover -s tests -p test_*.py
- Sintaxe: python -m py_compile ble_client_mpx5010dp.py pitaco24_monitor.py
- Validação física depende de teste do operador no Windows e ESP32-C3.
