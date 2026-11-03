# PITACO 2.4 — middleware Python para testar PPG e Gate 01

## Objetivo

Usar o aplicativo ble_client_mpx5010dp.py (CustomTkinter + Matplotlib)
como **testador principal**, aproveitando a GUI original de pressão e fluxo.
Acrescentamos **visualização dos dados realmente recebidos no PC** em uma segunda janela: curvas
RED/IR RAW, histórico de BPM qualificado, estado de contato, G1, taxa e perdas de sequência.
A tela pneumográfica original permanece separada, com seu próprio botão.

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
          ├── botão Gráfico Pneumo → janela original pressão/fluxo
          ├── botão Monitor Cardíaco / SpO2 → nova janela RED/IR e BPM
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
- open_graph / close_graph: exibem/escondem somente o pneumógrafo, sem parar PPG quando a outra janela está aberta.
- open_ppg_graph / close_ppg_graph: exibem/escondem somente a janela óptica, compartilhando o comando de aquisição com o pneumógrafo.
- update_plot: desenha somente o gráfico respiratório original.
- update_ppg_plot: desenha RED/IR sem filtrar, histórico de BPM qualificado e painel G1/contato/taxa/erros.
- SpO2 permanece explicitamente **não calculada**, sem gráfico fictício nem sentinela 0% na GUI.
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
| BPM | somente bpm_valid com contato e G1 aceitos; o histórico mostra lacunas quando inválido |
| SpO2 | não calculada, sem exibir 0% nem estimativa inventada |
| Pressão | quantidade de linhas legadas recebidas |
| CSV descartadas | perda na fila de gravação do PC, distinta da perda BLE |

## Ensaio Windows: BLE e USB sem trocar firmware

1. Atualizar a branch do middleware e executar o aplicativo Python com
   dependências atuais no Windows. O ESP32 pode manter o firmware anterior.
2. Selecionar **Bluetooth** ou **Cabo USB**. Para o teste isolado, definir
   portas virtuais do jogo como **Somente monitor**.
3. Clicar **Conectar**, depois **Gráfico Pneumo** (somente pressão/fluxo)
   ou **Monitor Cardíaco / SpO2** (RED/IR, BPM, G1, contato). Os botões
   controlam janelas independentes, mas compartilham a mesma aquisição.
   Abrir a segunda janela não repete o comando r, e fechar uma delas
   não envia f enquanto a outra continuar aberta.
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

## Escolha de LEDs e BPM

O sensor empregado é MAX30102 (canais RED e IR); o firmware usa
MAX30105.h como biblioteca SparkFun compatível, não como identificação
literal de um chip MAX30105 com LED verde. O baseline já inicializa
ledMode=2 (RED+IR), desliga o verde e chama checkForBeat(IR >> 3),
com RED/IR originais de 18 bits preservados na telemetria. Não habilitar
verde para a GUI: ele não é necessário para BPM em IR, e não existe no
MAX30102. SpO2 demanda algoritmo de oximetria e calibração/validação
própria; não é calculada nesta mudança de middleware.

## Referência função por função do middleware Python

### Transporte e parser (pré-existentes, reutilizados)

| Função | Arquivo | Entrada → operação → saída |
| --- | --- | --- |
| start_bridge | ble_client_mpx5010dp.py | Escolha da conexão/COM → abre porta e threads de monitoramento |
| ble_bridge | ble_client_mpx5010dp.py | BLE → descobre PITACO, assina pressão legacy + PPG JSON e inicia coleta no modo monitor |
| notification_handler | ble_client_mpx5010dp.py | Fragmentos da characteristic de pressão → reconstrói LF, encaminha pressão, echop e zero |
| ppg_notification_handler | ble_client_mpx5010dp.py | Fragmentos do canal óptico → remonta JSONL, contabiliza notificação e JSON inválido |
| usb_read_device_loop | ble_client_mpx5010dp.py | USB → lê LF/echop/zero/pressão/JSON e usa o mesmo parser |
| parse_pitaco_line | pitaco24_protocol.py | Linha → valida pressão numérica ou JSON sample/G1 e descarta estrutura inválida |
| BleJsonlBuffer.feed | pitaco24_protocol.py | Bytes BLE → acumula até LF e só entrega linha completa |
| process_pitaco_line | ble_client_mpx5010dp.py | Mensagem válida → atualiza monitor e preserva regras anteriores de pressão e BPM para Unity |
| update_pressure_from_device | ble_client_mpx5010dp.py | Pa → fluxo estimado, filtro e buffers do gráfico pneumográfico |
| PressureFilter.process | ble_client_mpx5010dp.py | Fluxo estimado → filtro configurável do pneumo, sem alterar RED/IR |
| interpolation_loop | ble_client_mpx5010dp.py | Fluxo/pressão → escreve série contínua na COM do jogo respiratório |
| oximeter_command_loop | ble_client_mpx5010dp.py | COM virtual oxímetro → responde echox e inicia/para por r/f |
| send_ble_command | ble_client_mpx5010dp.py | r/f/c/z → preserva envio pela characteristic original ou USB física |
| stop_bridge | ble_client_mpx5010dp.py | Desconexão → fecha janelas, finaliza CSV e libera COM/USB/BLE |

### Modelagem do teste (novo; não altera aquisição)

| Função | Arquivo | Operação |
| --- | --- | --- |
| PpgMonitor.reset | pitaco24_monitor.py | Zera contadores e históricos ao começar nova conexão |
| PpgMonitor.observe | pitaco24_monitor.py | Registra amostras/pressão/G1, seq uint16, gaps, duplicatas, contato e BPM qualificado |
| PpgMonitor.snapshot | pitaco24_monitor.py | Copia estado estável para GUI, sem acessar Tk nos callbacks |
| PpgMonitor.note_ble_fragment | pitaco24_monitor.py | Conta notificações recebidas do canal PPG |
| PpgMonitor.note_invalid_json | pitaco24_monitor.py | Conta linhas BLE completas inválidas; não deve ser confundido com G1 reprovado |
| PpgCsvRecorder.start | pitaco24_monitor.py | Abre caminho CSV e inicia thread escrita |
| PpgCsvRecorder.record | pitaco24_monitor.py | Enfileira RAW e eventos no callback sem bloquear escrita em disco |
| PpgCsvRecorder._writer | pitaco24_monitor.py | Consome fila, escreve linhas CSV e atualiza contador |
| PpgCsvRecorder.stop | pitaco24_monitor.py | Termina gravação e espera encerramento da thread |

### Interfaces independentes (novas e preservadas)

| Função | Papel |
| --- | --- |
| open_graph / close_graph | Abre/fecha só o gráfico pneumo; preserva aquisição se o painel óptico está aberto |
| open_ppg_graph / close_ppg_graph | Abre/fecha só monitor cardíaco; preserva aquisição se pneumo está aberto |
| update_plot | Mantém fluxo/pressão e escalas originais |
| update_ppg_plot | Desenha RAW RED/IR, histórico BPM e indicadores G1, contato, erros e throughput |
| toggle_ppg_csv | Controla gravação opcional a partir do painel óptico |

O início da aquisição é compartilhado: em modo somente monitor a ponte já
envia r ao conectar; abrir qualquer gráfico **não deve repetir r** se
is_sampling já está ativo. Nenhum gráfico roda processamento SQI novo.

## Modo experimental PC: BPM e SpO₂ ilustrativa (opt-in, sem firmware novo)

Disponivel **somente** no painel `Monitor Cardíaco / SpO₂`: habilitar a
checkbox **Calcular BPM e SpO₂ experimentais NO PYTHON (não calibrados)**.
Desligada por padrão; funciona igualmente por USB ou BLE, pois utiliza
somente mensagens `sample` RED/IR já recebidas. Não muda a caracteristica
GATT, firmware, sensor, G1, pressão, CSV RAW ou dados enviados à Unity.

**Apresentacao:** legenda `FW qualificado` (roxo) = BPM fornecido pelo
ESP32 com `bpm_valid=true`; `Python EXP.` (amarelo) = BPM independente
calculado no PC; e gráfico `SpO₂ EXP. (%)` (verde) = DEMONSTRAÇÃO NÃO
CALIBRADA. O painel mostra também índice R e motivo de indisponibilidade.
Sem sinal, o gráfico tem lacunas/valor `--`, nunca interpola ou inventa
medição. SpO₂ experimental **não é dispositivo médico nem prova de precisão**.

### Como o cálculo é feito (pitaco24_experimental.py)

1. Receber pares sincronizados RED/IR e `t_ms` (~25 Hz); descartar para
   estimativa qualquer amostra sem contato ou sem `sqi.g1=true`.
   Amostras inválidas permanecem preservadas no gráfico RAW e CSV.
2. Formar 8 segundos contínuos de dados (pelo menos 7,5 s, 160 amostras),
   testar continuidade, amostragem e presença de sinal óptico.
   Mudança de contato ou gap reinicia a janela experimental.
3. Para cada canal, remover DC variável por média móvel centrada de
   aproximadamente 1 s e suavizar com 3 pontos para estimar componente AC.
4. Estimar BPM pelo atraso de maior autocorrelação normalizada do IR
   em 35–200 bpm; exigir regularidade (limiar experimental 0,57).
5. Obter o índice de razão de razões
   `R = (RMS(RED_AC)/media(RED)) / (RMS(IR_AC)/media(IR))`.
   Exigir coerência entre canais (correlação > 0,70) e descartar
   grandes variações de nível óptico (>12% de DC na janela).
6. Aplicar **somente para demonstração** a aproximação encontrada
   no exemplo Maxim/SparkFun:
   `SpO₂_demo = -45.060 × R² + 30.354 × R + 94.845`,
   dentro do domínio experimental de R; fora do domínio, mostrar `--`.
   Essa curva **não foi calibrada para o PITACO, para a pessoa testada,
   para o encaixe óptico nem para o dispositivo usado**. Um valor plausível
   não equivale a aferição de saturação.

A atualização ocorre a cada ~1 segundo de telemetria; todo cálculo é no
PC, independente do filtro do pneumógrafo, e só quando a checkbox está
ativa. O resultado experimental NÃO alimenta o contrato de jogo
`FC,SpO2`: a saída original da Unity continua transmitindo somente BPM
qualificado do firmware quando permitido, com SpO₂ indisponível.

**Referências técnicas do algoritmo, não provas de acurácia:**

- Analog Devices/Maxim, *MAX3010x EV Kits Recommended Configurations and
  Operating Profiles*, seção SpO2, fórmula de ratio-of-ratios e necessidade
  de calibração empírica:
  https://www.analog.com/media/en/technical-documentation/user-guides/max3010x-ev-kits-recommended-configurations-and-operating-profiles.pdf
- SparkFun, `spo2_algorithm.h`, algoritmo de demonstração Maxim,
  `FreqS=25` e curva ilustrativa:
  https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library/blob/master/src/spo2_algorithm.h
- Analog Devices, datasheet MAX30102:
  https://www.analog.com/media/en/technical-documentation/data-sheets/max30102.pdf

### Roteiro de validação experimental

- Conectar via USB; abrir o monitor óptico; com dedo estável, marcar BPM
  obtido por firmware e por Python **frente a oxímetro/medidor cardíaco de
  referência** durante 60 s. Registrar CSV (RAW, G1, contato).
- Repetir via BLE sem trocar firmware e comparar taxa, perdas e BPM.
- Retirar o dedo por 10 s e recolocar: ambos os indicadores experimentais
  precisam ficar indisponíveis e voltar somente após nova janela aceita.
- Fazer movimento proposital: verificar rejeições e lacunas; não confundir
  G1 PASS com ausência comprovada de artefato de movimento.
- Registrar erro absoluto (BPM), tendência e dispersão em vários testes,
  além de resultados com diferentes posições, pressão de contato e
  iluminação. Para SpO₂, comparação com oxímetro comercial é apenas
  exploratória, não substitui calibração clínica contra saturação arterial.
