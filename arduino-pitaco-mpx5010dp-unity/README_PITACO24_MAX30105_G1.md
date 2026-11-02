# PITACO 2.4 — MAX30105 + Gate 01 (prototipo experimental)

Sensor fisico informado: MAX30105. Firmware de origem: ramo
fix/usb-bridge-grafico do PITACO MPX5010DP/ESP32. Biblioteca utilizada:
SparkFun MAX3010x Pulse and Proximity Sensor Library (MAX30105.h).

## Estrategia de aquisicao
- MAX30105 possui canais RED, IR e GREEN; sensor de origem e de deteccao optica
  de particulas. Aqui usamos PPG como pesquisa, NAO como dispositivo medico.
- Modo de operacao padrao: LED_MODE=2 (RED + IR), 100 Hz de sample rate,
  FIFO-average=4, pulse width 411 us (ate 18 bits) e adcRange=4096.
- GREEN opcional: configurar PITACO24_ENABLE_GREEN=1 em ppg_max30105.h,
  habilitando LED_MODE=3 e coleta RED + IR + GREEN.
- G1 avalia SOMENTE RED/IR mesmo no modo com GREEN. GREEN serve para
  caracterizacao do sinal e possiveis experimentos futuros.
- Em ambos os modos o firmware continua usando a mesma biblioteca MAX30105.h.

## Fios e pinagem (HIPOTESES — verificar fisicamente)

MPX5010DP mantido no GPIO0 da versao experimental do PITACO.
MAX30105 I2C: SDA=GPIO4, SCL=GPIO5, por enquanto.
Confirmar quais pinos sao expostos e livres na placa ESP32 efetivamente usada.
A alimentacao depende do breakout: conferir regulador e pull-ups; nao
aplicar 5 V diretamente aos sinais I2C de um ESP32 3.3 V.
Endereço I2C usual 0x57; a biblioteca verifica PART_ID=0x15, mas esse codigo
de identificacao e compartilhado entre MAX30102 e MAX30105. O modelo real
deve ser confirmado visualmente na placa/BOM.

## Firmware e sua arquitetura

arquivos:
- arduino-pitaco-mpx5010dp-unity.ino: pressao, comandos, USB/BLE/OTA, loop.
- ppg_max30105.h / ppg_max30105.cpp: MAX30105, FIFO, 18-bit, RED/IR/GREEN opcional.
- sqi_gate1.h / sqi_gate1.cpp: G1 streaming para RED e IR.

Status dos gates: apenas G1. Thresholds de G1 eram empiricos com MAX30102
e exigem recalibracao para MAX30105, montagem real, posicao do dedo e pegador.

## Saida USB 115200 baud

Mantem pressao numerica legada e o comando echop.

Novas linhas:
- Modo padrao: R,seq,receive_ms,window,red,ir
- Modo GREEN:  R,seq,receive_ms,window,red,ir,green
- Resultado G1: Q,window,end_ms,pass,reason,samples
- Sucesso: X,PPG_READY,MAX30105,CHANNELS,RED_IR,G1_ONLY
  ou X,PPG_READY,MAX30105,CHANNELS,RED_IR_GREEN,G1_ONLY
- Falha I2C: X,PPG_ERROR,MAX30105_NOT_FOUND
- Identificacao indicativa: X,PPG_IDENT,MAX30105_ASSUMED,PART_ID,0x15,REV,0xNN

receive_ms e momento da retirada do FIFO, nao da conversao ADC.
A janela G1 dura 5 s. Motivos G1:
0 OK; 1 NO_SAMPLES; 2 RED_LOW; 3 IR_LOW; 4 RED_FLAT;
5 IR_FLAT; 6 RED_CLIP; 7 IR_CLIP; 8 TOO_FEW; 9 ACQUISITION_GAP.

## BLE

Mantida characteristic de pressao: 3bcdff27-47fc-4a87-9684-7672c49d9266.
Nova characteristic PPG NOTIFY: 3bcdff2a-47fc-4a87-9684-7672c49d9266.
Servico: 0f128d4d-3cf9-46de-bb31-ed159450d6cf.

Pacotes binarios little-endian:
- 0x01 (16B): A5 01 | seq:u16 | window:u16 | ms:u32 | red:u24 | ir:u24
- 0x03 (19B): A5 03 | seq:u16 | window:u16 | ms:u32 | red:u24 | ir:u24 | green:u24
- 0x02 (12B): A5 02 | window:u16 | ms:u32 | pass:u8 | reason:u8 | count:u16

Pacote 0x03 aparece apenas quando modo GREEN esta habilitado e ainda cabe em
20 bytes de carga ATT numa notificacao BLE com MTU padrao=23.

## Validacao

1. Confirmar fisicamente o modelo MAX30105, seus pinos e tensoes.
2. Compilar e gravar no ESP32 real com Arduino Core e SparkFun MAX3010x.
3. Com USB conectado, enviar e e depois r, verificar pressao e RAW.
4. Testar sem dedo / dedo estavel por pelo menos tres janelas de 5 s.
5. Coletar CSV (modo RED+IR):
   python3 -m pip install pyserial
   python3 pitaco24_ppg_probe.py /dev/ttyACM0 --seconds 35
   (trocar por COM3 no Windows).
6. Alterar PITACO24_ENABLE_GREEN=1, recompilar, refazer o teste. Agora o CSV
   deve incluir a coluna green; o Gate 01 deve permanecer RED/IR.
7. Testar BLE, preservacao do canal de pressao e contagem de pacotes.
8. Executar comando z/c e observar se o firmware continua adquirindo PPG
   sem perdas significativas de FIFO.
9. Revisar thresholds G1 usando capturas reais do MAX30105.

Testes host:
g++ -std=c++11 -Wall -Wextra -Werror -I. sqi_gate1.cpp tests/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1
python3 -m unittest discover -s tests -p 'test_*.py'

## Limitacoes
- O MAX30105 nao tem validacao clinica de SpO2 neste projeto.
- G1 PASS nao e autorizacao para usar SpO2 clinica ou para acionar protecao.
- Os parametros do G1 foram pesquisados/observados no MAX30102, NAO
  recalibrados ainda para o sensor MAX30105 real.
- A biblioteca SparkFun usa buffer interno pequeno. Serial, BLE e calibracao
  da pressao devem ser testados juntos para identificar atrasos/perdas.
- Ainda sem compilacao verificada de todo firmware no ESP32, sem bancada,
  sem calculo de FC/SpO2 no PC e sem integracao no Unity.
- A ponte Python atual precisa reconhecer linhas de telemetria PPG R e Q.

## Fontes
MAX30105 datasheet:
https://www.analog.com/media/en/technical-documentation/data-sheets/MAX30105.pdf
SparkFun MAX3010x:
https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library
Hookup:
https://learn.sparkfun.com/tutorials/max30105-particle-and-pulse-ox-sensor-hookup-guide
Historico G1:
https://github.com/PHV00/RFC-MelhoriaProjetoIBlueIt
