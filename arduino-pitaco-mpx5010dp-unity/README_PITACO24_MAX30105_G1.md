# PITACO 2.4 — MPX5010DP + MAX30105 + G1 + BPM experimental

**Local atual do firmware 2.4:** `firmware/pitaco_2_4/pitaco_2_4.ino` (oito outras abas `.ino` na mesma pasta). **Interface Python:** `ble_client_mpx5010dp.py` na raiz do projeto. Algumas referências adiante registram etapas históricas e não representam o layout de compilação atual.

**Documentação do baseline:** [Visão geral](docs/BASELINE.md) · [Gate 01 e suas funções](docs/GATE_01.md) · [BLE, USB e ponte Unity](docs/BLE_USB.md). Capturas CSV locais ficam fora do Git.


## Objetivo e arquitetura atual

**ATENCAO:** este README foi originalmente escrito para o prototipo de
dois arquivos .ino. Seu restante conserva varias referencias historicas,
inclusive a antiga COM virtual do oximetro, que **foi removida** do
middleware. Para arquitetura e contratos correntes consulte:
[mapa SoC de todas as abas .ino](docs/SOC_INO_TABS.md),
[baseline atualizado](docs/BASELINE.md),
[documentacao de BLE/USB](docs/BLE_USB.md) e
[interface modular Python](docs/MIDDLEWARE_MODULAR.md).

O ESP32-C3 continua lendo o MPX5010DP (~20 Hz) e o MAX30102
(~25 pares RED/IR por segundo). A implementacao agora usa **separacao
de responsabilidades**: orquestrador principal, comandos, respiracao,
BLE/OTA, aquisicao PPG, contato/G1, BPM e serializacao JSON em abas
`.ino`. O driver SparkFun local permanece em `firmware/pitaco_2_4/src/vendor_sparkfun_max3010x/`
com a correcao FIFO64, pois o Arduino compila o driver de terceiros como
`.h/.cpp`; nao o renomeamos para `.ino`. A interface Python atual
preserva a unica COM do jogo respiratorio e nao abre segunda COM do
oximetro.

## Biblioteca e GPIOs

Firmware Arduino Core ESP32 (placa ESP32-C3 conforme branch de origem).
Adicionar a biblioteca SparkFun MAX3010x Pulse and Proximity Sensor Library
(inclui MAX30105.h e heartRate.h).

MPX5010DP: GPIO0 existente.
MAX30105: SDA GPIO4, SCL GPIO5, pinos PROVISORIOS.
Antes de energizar, revisar pinagem real, VCC/VIN do breakout, pull-ups
I2C e niveis logicos 3.3 V do ESP32. Nao presumir que todo breakout
MAX30105 aceita 5 V.

Setup MAX30105: 100 Hz configurados, FIFO-average=4 (~25 amostras/s
efetivas), dois LEDs RED+IR, green desligado, largura 411 us (18 bits).
O MAX30105 nao e um oximetro medico certificado; seu uso aqui e pesquisa.

## Controle de aquisicao e integridade FIFO

O MAX30105 opera em dois estados para impedir o problema de bancada
`ovf=31,wr=0,rd=0,novas=0,G1 NO_SAMPLES`:

- **STOPPED**: ao ligar e quando `isSampling` e falso, durante `z`
  (zero da pressao) ou durante OTA, o chip entra em `shutDown()`;
  conserva I2C ativo, mas nao produz amostras opticas.
- **COLLECTING**: apos `r`, com pressao calibrada, o chip passa por
  `wakeUp()`; a FIFO e reinicializada **uma vez na transicao** para
  remover dados obsoletos do estado parado. O loop chama `check()`,
  processa todos os pares RED/IR disponiveis em G1/BPM e os transmite.
- **STOPPED novamente**: `f`, `e` (handshake que interrompe sessao),
  `z` e OTA fazem o chip parar. A janela G1 parcial e descartada
  deliberadamente no comando de parada.
- **Falha real de FIFO**: `ovf>0` marca `GAP` no G1; processa primeiro
  as amostras ainda recuperaveis e so entao `clearFIFO()` reabilita
  a aquisicao. `novas>disponiveis` identifica perda no pequeno buffer
  circular de software da SparkFun e tambem invalida a janela.

Status USB: `X,PPG_STATE,STOPPED`, `X,PPG_STATE,COLLECTING`,
`X,PPG_FIFO_OVERFLOW`, `X,PPG_FIFO_RECOVERED`,
`X,PPG_SW_RING_OVERRUN` e `X,PPG_DIAG` (contagem a cada 2 s).
O diagnostico periodico pode ser desabilitado com `#define PPG_DIAG false`.

**Importante:** esta implementacao conserva os dois arquivos `.ino` e a
comunicacao legada. Nao resolve por si so eventuais bloqueios ou baixa
vazao BLE durante captura real; perdas devem ser medidas na placa.
Consulte `README_TESTE_FIFO_PPG.md` para protocolo de validacao.

## Serial USB e BLE

O protocolo numerico de pressao continua ativo, 115200 baud por USB e
caracteristica BLE original para preservar os clientes atuais.
Comandos herdados e/r/f/c/z, echo echop e OTA mantidos.

Tambem sao enviadas linhas JSON pela USB e pela characteristic PPG BLE:
service UUID: 0f128d4d-3cf9-46de-bb31-ed159450d6cf
pressao legado: 3bcdff27-47fc-4a87-9684-7672c49d9266
JSON PPG notify: 3bcdff2a-47fc-4a87-9684-7672c49d9266

Exemplo de amostra (valores ilustrativos):
{"type":"sample","seq":15,"t_ms":10400,"ppg":{"red":109840,"ir":122963,"bpm":72.5,"bpm_valid":true},"mpx5010dp":{"pressure_pa":14.5,"valid":true},"sqi":{"g1":true,"reason":0}}

O campo bpm passa a ser null e bpm_valid=false quando nao ha estimativa
disponivel ou o G1 nao aprovou a janela mais recente.
g1=null significa janela inicial ainda nao avaliada (5 s).
A pressao e a amostra do PPG possuem frequencias de aquisicao diferentes:
o campo pressure_pa e o ultimo valor de pressao conhecido, nao uma leitura
simultanea ao instante da conversao de RED/IR. t_ms e o momento de leitura
da FIFO, nao o timestamp de conversao do ADC.

JSON G1 separado a cada ~5s:
{"type":"g1","t_ms":15000,"window":3,"sqi":{"g1":true,"reason":0,"samples":125}}

BLE GATT: uma mensagem JSON inclui LF e pode ultrapassar o payload
minimo de notificacao de 20 bytes (ATT MTU=23). O firmware transmite
o JSON em pedacos de ate 20 bytes na mesma characteristic, ordenados,
e a ponte Python concatena ate LF. Isso evita truncamento por MTU minimo,
mas gera MULTIPLAS notificacoes por amostra. A confiabilidade de BLE
a ~25 amostras/s junto com a caracteristica legada de pressao precisa
ser demonstrada em bancada sob carga. Notificacoes BLE nao garantem entrega;
monitorar sequencias perdidas e gaps de FIFO antes de afirmar equivalencia USB.
O PC nao pode enviar e/r/f diretamente a characteristic JSON; comandos
continuam na characteristic BLE original.

## BPM e SpO2

O BPM do firmware deriva de checkForBeat(IR), presente na SparkFun. O
RAW IR de 18 bits e reduzido por deslocamento de 3 bits apenas na entrada
do detector: o codigo da biblioteca usa uint16_t/int16_t internamente.
Os valores RAW originais de 18 bits seguem intactos no JSON e no G1.
O escalonamento do detector e experimental e precisa de teste no dedo.
Depende
de detectar pulsos plausiveis e de G1 PASS. E um VALOR EXPERIMENTAL,
nao validado clinicamente para MAX30105. Nao confundir deteccao de pulso
com estimativa clinica de frequencia cardiaca.

O algoritmo Maxim do I Blue It original (spo2_algorithm.h) e nossa
principal referencia historica para uma futura comparacao de BPM/SpO2,
mas sua funcao original de coleta bloqueante NAO foi copiada ao ESP32.
O estimador de BPM do repositorio RFC permanece experimental e NAO e
a base deste firmware.

SpO2 NAO e calculada por este codigo. Para a interface serial original
do Unity, a ponte opcional transmite "BPM,0" somente quando BPM e G1
estao validos. O zero e sentinela de SpO2 indisponivel, e NAO uma medicao
de oxigenacao. O Unity atual pode exibir "0%" por nao reconhecer status
de indisponibilidade; isto requer um tratamento de UI antes de qualquer
demonstracao de SpO2 ao paciente.

## Ponte Python / Unity

Executar ble_client_mpx5010dp.py no Windows com as dependencias originais.
A interface agora oferece:
- Porta ESP32 (USB), quando se usa cabo.
- Porta Jogo (Virtual): canal respiratorio existente, com echop.
- Porta Oxímetro (Virtual): canal OPCIONAL, com echox e FC,0.
- Seletor original Bluetooth / Cabo USB.

Os dois canais virtuais devem usar portas distintas e pares com0com
configurados para cada controlador do Unity; nao selecionar a mesma COM
fisica duas vezes. O ramo original do Unity pode permanecer sem mudancas
para a pressao. O controlador Oximetro ja conhece FC,SpO2, mas sua
ativacao no Unity e codigo de UI devem ser inspecionados antes do uso.

O parser minimo e testavel em pitaco24_protocol.py; JSON de PPG e
traduzido pelo bridge em vez de repassar diretamente para a Unity,
que continua recebendo seu formato antigo.

## Teste bancada

1. Confirmar SDA/SCL, placa, alimentacao e biblioteca SparkFun.
2. Compilar com Arduino IDE ou arduino-cli ESP32-C3.
3. Usar cabo primeiro: observar echop, pressao numerica e JSON sample.
4. Com o dedo estavel, medir taxa de amostras, g1 e bpm. Sem dedo e com
   movimento, verificar que bpm_valid fica falso quando necessario.
5. Testar calibracoes c e z; observar gaps, travamentos e continuidade
   da pressao.
6. Testar Bluetooth e comparar seq e desempenho com USB. Se houver gaps,
   revisar transporte antes de utilizar G2/G3/G4 e BPM no jogo.
7. Conectar duas COM virtuais (pressao e oxímetro), confirmar echop / echox
   e que a Unity recebe pressão e o BPM apenas no respectivo controlador.

Teste host na pasta do firmware:
g++ -std=c++11 -Wall -Wextra -Werror tests/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1
python3 -m unittest discover -s tests -p 'test_*.py'

## Pendencias

- Compilacao e gravacao no ESP32 real e testes de sensor/USB/BLE.
- Calibracao dos thresholds G1 para MAX30105 real.
- Verificacao da acuracia BPM contra referencia confiavel.
- Validacao quantitativa do calculo de fluxo do MPX5010DP.
- Processamento G2/G3/G4, SpO2 calibrada e treinamento ML-Agents.
- Tratar a ausencia de SpO2 na UI do Unity sem exibir 0% como se fosse
  medida real.

Fontes:
- MAX30105/SparkFun: https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library
- Firmware original I Blue It:
  https://github.com/UDESC-LARVA/iblueit-psychophysiological-flow
- Firmware base PITACO: branch fix/usb-bridge-grafico
