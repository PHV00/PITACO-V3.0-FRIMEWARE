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
          └── BPM e SpO2: apenas monitor local, sem COM adicional

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
- SpO₂ **não é calculada pelo firmware**; a GUI calcula automaticamente uma demonstração experimental no PC quando G1/contato e janela de dados permitem, sem exibir 0% fictício.
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
| SpO₂ | estimativa Python experimental automática quando disponível; sem sinal, `--` e lacuna no gráfico |
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
- A Unity continua com a COM virtual de pressão/fluxo do jogo respiratório.
  O BPM e a SpO₂ experimentais são exibidos localmente, sem COM virtual
  adicional e sem novo contrato de integração com a Unity.
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
própria; a SpO₂ ainda não é calculada no firmware. No PC há apenas uma estimativa demonstrativa não calibrada.

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
| process_pitaco_line | gui/main_window.py | Mensagem válida → atualiza monitor PPG e pressão do jogo (BPM fica no monitor) |
| update_pressure_from_device | ble_client_mpx5010dp.py | Pa → fluxo estimado, filtro e buffers do gráfico pneumográfico |
| PressureFilter.process | ble_client_mpx5010dp.py | Fluxo estimado → filtro configurável do pneumo, sem alterar RED/IR |
| interpolation_loop | ble_client_mpx5010dp.py | Fluxo/pressão → escreve série contínua na COM do jogo respiratório |
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

## Monitor experimental PC: BPM e SpO₂ ilustrativa (automático, sem firmware novo)

Os cálculos Python iniciam automaticamente com o monitor de aquisição,
**mesmo que a janela gráfica não esteja aberta**. Não existe mais checkbox
para habilitar/desabilitar BPM e SpO₂ experimentais. A janela mostra os
históricos diretamente quando aberta, usando as mensagens `sample` RED/IR
já recebidas por USB ou BLE.

A tentativa de cálculo ocorre a cada ~400 ms com janela progressiva:
a primeira estimativa pode aparecer após aproximadamente 3 segundos de
contato e dados contínuos; a janela móvel cresce até 8 segundos.
O G1 não bloqueia o cálculo Python de bancada: é exposto separadamente
como **aviso de qualidade**, assim como contato, baixa AC, movimento
suspeito e baixa coerência RED/IR. O firmware continua exigindo
G1 aprovado para aceitar seu próprio BPM. BPM Python depende de periodicidade
IR; SpO₂ DEMO depende da razão RED/IR e **não exige BPM Python válido**.
Ambos podem existir como candidatos mesmo com G1 reprovado; isto não implica
confiabilidade fisiológica. Limites matemáticos e da curva de demonstração
continuam podendo deixar uma estimativa em `--`.
Não altera GATT, firmware, sensor, Gate 01, pressão, CSV RAW ou Unity.

**Apresentacao:** legenda `FW qualificado` (roxo) = BPM fornecido pelo
ESP32 com `bpm_valid=true`; `Python EXP.` (amarelo) = BPM independente
calculado no PC; e gráfico `SpO₂ EXP. (%)` (verde) = DEMONSTRAÇÃO NÃO
CALIBRADA. O painel mostra também índice R e motivo de indisponibilidade.
Sem sinal, o gráfico tem lacunas/valor `--`, nunca interpola ou inventa
medição. SpO₂ experimental **não é dispositivo médico nem prova de precisão**.

### Como o cálculo é feito (`pitaco_bridge/experimental.py`)

1. Receber pares RED/IR e `t_ms` (~25 Hz). **Contato e G1 são
   metadados de qualidade**, não condições de aprovação das equações de
   bancada. Uma transição de contato reinicia somente a janela móvel
   para evitar mistura de trechos, preservando os resultados históricos.
   RAW e CSV permanecem intocados.
2. Formar janela progressiva com pelo menos ~3 s contínuos (70 amostras e
   3 s reais), estendendo até 8 s. Gaps e timestamps impossíveis reiniciam
   só a janela de cálculo, com marcador de lacuna no gráfico. O limite
   de autocorrelação `len(y)//3` exige vários ciclos para BPM lento.
3. Para cada canal, remover DC variável por média móvel centrada de
   aproximadamente 1 s e suavizar com 3 pontos para estimar componente AC.
4. Estimar BPM pelo atraso de maior autocorrelação normalizada do IR
   em 35–200 bpm; a periodicidade mínima de 0,57 evita selecionar um
   atraso sem evidência de ritmo.
5. Independentemente do BPM, estimar a razão
   `R = (RMS(RED_AC)/media(RED)) / (RMS(IR_AC)/media(IR))`.
   Coerência RED/IR baixa (<0,70), grande variação de DC (>12%), falta
   de contato e G1 reprovado geram **avisos** visíveis, não falsos PASS.
   Denominadores nulos e valores fora do domínio do modelo não geram SpO₂.
6. Aplicar **somente para demonstração** a aproximação encontrada
   no exemplo Maxim/SparkFun:
   `SpO₂_demo = -45.060 × R² + 30.354 × R + 94.845`,
   dentro do domínio experimental de R; fora do domínio, mostrar `--`.
   Essa curva **não foi calibrada para o PITACO, para a pessoa testada,
   para o encaixe óptico nem para o dispositivo usado**. Um valor plausível
   não equivale a aferição de saturação.

A atualização ocorre a cada ~400 ms de telemetria; todo cálculo é no
PC, independente do filtro do pneumógrafo, automaticamente durante a
coleta com qualquer estado de G1/contato, sem botão de habilitação. O resultado experimental **não é transmitido à Unity**. Esta versão da ponte
mantém somente a COM virtual de pressão/fluxo para o jogo respiratório.
O monitor recebe RED/IR, BPM e SQI pelo JSON do ESP32, sem COM adicional.

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

## Interpretação dos três gráficos e leitura instantânea (2026-11-02)

O painel **Monitor Cardíaco / SpO₂** tem três gráficos de cima para baixo:

1. **PPG RAW (RED e IR):** contagens brutas dos dois LEDs. Ondulações
   repetidas são candidatas a pulso; não representam, por si, BPM validado.
2. **BPM (gráfico central):** curva roxa = BPM aceito do firmware ESP32
   (função SparkFun `checkForBeat`, `bpm_valid=true`); curva amarela =
   BPM **experimental** por autocorrelação do IR calculada no Python
   (automaticamente, após janela válida). Valores do eixo vertical são escala,
   não medição atual. Os números continuam no gráfico e aparecem também
   no **primeiro cartão do canto superior direito**, com as duas fontes
   identificadas (`ESP32` e `Python EXP.`); sem valor, mostram `--`.
3. **SpO₂ EXP.:** estimativa ilustrativa não calibrada. O **segundo cartão
   do canto superior direito** mostra o valor instantâneo (ou `--`);
   o gráfico inferior mantém o histórico, com lacunas sem sinal.

**Por que pode ficar `--` mesmo com G1 PASS?** O G1 verifica integridade
básica de janela e contato, **não** comprova batimentos detectáveis.
O firmware só emite BPM após detecções plausíveis de `checkForBeat`,
janela G1 válida e batimento recente. O analisador Python é automático,
independente de G1 e contato para **teste diagnóstico**, começa a estimar
a partir de ~3 s conforme o ritmo e calcula SpO₂ DEMO sem exigir BPM.
Incoerência RED/IR, baixa AC e movimentos ficam expostos como alertas.
Os resultados anteriores são preservados na memória limitada da sessão.
A linha superior agora indica o motivo do firmware:
`Aguardando G1`, `G1 reprovado`, `Sem contato`,
`Firmware ainda sem BPM valido`, `BPM firmware valido` ou
`Sem amostras recentes`. A linha experimental exibe seu próprio motivo.

O **índice R** é a variável intermediária do cálculo de SpO₂
(`(AC_RED/DC_RED)/(AC_IR/DC_IR)`), e não a ordenada do gráfico central.
Ele é mostrado junto do estado experimental quando disponível.
Nenhum valor experimental é transmitido à Unity.

## Separação de cálculo/qualidade e persistência visual (04/11/2026)

- O algoritmo Python apresenta candidatos BPM e SpO₂ DEMO **independentes**,
  quando seus respectivos critérios matemáticos permitem. Não há promoção
  automática desses valores para o firmware, Unity ou segurança clínica.
- O painel mostra uma linha **Qualidade (diagnóstico)** separada dos números:
  contato, G1 e alertas de DC, AC, movimento e coerência são visíveis.
- Ao faltar amostras/timestamp íntegro, a estimativa **atual** mostra `--`;
  os pontos históricos não são apagados. A quebra gera uma lacuna, não uma
  linha falsa para 0 bpm ou 0% de SpO₂.
- A vista RAW agora exibe cerca de **30 segundos**, com 850 amostras na
  memória da GUI. Se houver reinício real da sequência do dispositivo,
  o monitor zera as séries RAW e BPM do firmware por sessão; o evento
  aparece no indicador `Reinícios seq`.
- O CSV original continua sendo a fonte de amostras brutas para análise
  offline; os valores de SpO₂ são apenas diagnósticos e não calibrados.

## Correção: candidato matemático x valor exibido sem contato (04/11/2026)

A curva Maxim/SparkFun usada por `estimate_experimental` é apenas uma
**aproximação demonstrativa não calibrada**. A presença de uma razão R
numérica NÃO comprova presença de dedo ou SpO₂: ruído no LED RED/IR pode
produzir valores plausíveis, inclusive próximos de 95–100%.

O `ExperimentalPpgAnalyzer` preserva agora os valores internos
`bpm_candidate` e `spo2_candidate` mesmo para experimentos sem contato.
Porém, os campos públicos da interface `bpm` e `spo2` são `None`
quando `sqi.contact` não é `true` ou os valores ópticos instantâneos
estão abaixo do mínimo de bancada (RED/IR < 5000). No caso da SpO₂,
também se suprime a **apresentação** se as amplitudes AC são pequenas ou
RED/IR são incoerentes; a fórmula bruta e seus avisos continuam disponíveis.
**O Gate 01 não bloqueia o cálculo Python nem substitui a condição de contato.**

A GUI deve exibir `SpO₂: -- | SEM CONTATO — candidato DEMO oculto`
na ausência de dedo; ao voltar o contato, o buffer de estimativa recomeça
e leva cerca de 3 s para produzir nova estimativa. Os pontos anteriores
do gráfico são preservados, com lacuna explícita durante a ausência do dedo.
A medição BPM qualificada do ESP32 segue inalterada, e nenhuma SpO₂ é
transmitida para a Unity.

O arquivo de bancada analisado em 04/11/2026 tinha 600 amostras em
aproximadamente 24 s, `contact=false` e G1 reprovado em toda a captura,
RED médio ~1418 e IR médio ~1007. Isso explica por que nenhum valor
de SpO₂ deve ser exibido nessa janela. O CSV individual não é armazenado
no repositório.

## Quatro cartões de monitoramento e médias móveis de 60 segundos

O cabeçalho óptico está organizado em duas linhas: **BPM atual | BPM médio
60 s** e **SpO₂ atual | SpO₂ média 60 s**. O cartão BPM médio exibe
**duas médias distintas**, firmware ESP32 e estimativa Python; não mistura
as fontes. O cartão SpO₂ média usa somente estimativas experimentais já
liberadas para apresentação, não as contagens RED/IR nem
`spo2_candidate`. Ambos os cálculos continuam sendo de bancada e não
estão calibrados para uso clínico.

A função `_rolling_mean_by_seconds` em `pitaco_bridge/monitor.py` agrupa
leituras numéricas pelo segundo do dispositivo, calcula a média de
cada segundo e depois a média dos segundos válidos presentes na janela
deslizante de 60 s. Assim, um segundo com 25 mensagens de firmware não tem
mais peso do que um segundo com menos mensagens. Instantes sem estimativa
não são interpolados nem tratados como zero. São necessários ao menos
**3 segundos com estimativas** para mostrar uma média inicial.

Antes de reunir uma janela completa, cada média é **parcial**.
O estado **completa** exige 60 s transcorridos desde o início do trecho
contínuo de contato e pelo menos 45 segundos contendo estimativas da
respectiva fonte; caso contrário continua parcial. A cobertura é
exibida em segundos na interface. O G1 continua com o comportamento
original em cada fonte: firmware qualificado depende de G1, Python não.

Ao perder contato, a média corrente mostra `--` imediatamente. Ao
recuperar o contato, começa um novo trecho de média; não mescla estimativas
da colocação anterior, mas mantém histórico dos gráficos. Sem novas
amostras por 2 s, os quatro indicadores ficam indisponíveis. O histórico
RAW na tela continua com aproximadamente 30 s (850 pontos), enquanto
um buffer **independente de 1.800 leituras** guarda o BPM firmware para
a média de 60 s. O analisador Python já conserva 300 estimativas
(aproximadamente 120 s a cada 400 ms).
