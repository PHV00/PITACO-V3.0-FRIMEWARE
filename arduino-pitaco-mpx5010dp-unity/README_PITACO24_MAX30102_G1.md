# PITACO 2.4 — MAX30102 + Gate 01 (prototipo experimental)

Base: branch fix/usb-bridge-grafico, SHA 17eabe9c2bdb80a930d536d28769fc61ad03bf2f.

## Implementado
- Firmware original de pressao mantido (MPX5010DP, USB serial, BLE, OTA).
- Aquisição RED/IR com SparkFun MAX3010x Pulse and Proximity Sensor Library (MAX30105.h).
- G1 independente, com integridade RAW e janelas de 5 segundos.
- Telemetria USB e característica BLE separada. NAO calcula SpO2/FC no ESP32.
- Testes sinteticos de G1 em tests/test_sqi_gate1.cpp.

## Pinagem — hipótese, não validada fisicamente
GPIO0 = pressao do firmware personalizado; I2C SDA=GPIO4, SCL=GPIO5 (valores
temporarios herdados do experimento ESP32-C3 no RFC). Confirme a placa e
a alimentacao 3.3 V / tolerancia do breakout antes de ligar.
Altere ppg_max30102.h para a sua fiação.

## Preparação
Instalar Arduino Core ESP32 e biblioteca SparkFun MAX3010x; abrir
arduino-pitaco-mpx5010dp-unity.ino com seus .h/.cpp na mesma pasta.

## USB — protocolo experimental
A saida numerica simples de pressao do PITACO foi preservada.
Registros adicionais:
- R,seq,receive_ms,window,red,ir
- Q,window,end_ms,pass,reason,samples
- X,PPG_READY,G1_ONLY ou X,PPG_ERROR,MAX30102_NOT_FOUND

timestamp receive_ms = momento de retirada do FIFO, NAO instante exato da conversao.
Os campos red/ir preservam ate 18 bits, sem truncamento para uint16_t.
A janela Q avalia as amostras R com o mesmo window ID.
Reason: 0 OK; 1 NO_SAMPLES; 2 RED_LOW; 3 IR_LOW; 4 RED_FLAT;
5 IR_FLAT; 6 RED_CLIP; 7 IR_CLIP; 8 TOO_FEW; 9 ACQUISITION_GAP.

## BLE
Caracteristica de pressao original: 3bcdff27-47fc-4a87-9684-7672c49d9266
Nova caracteristica PPG: 3bcdff2a-47fc-4a87-9684-7672c49d9266
Mesmo service UUID: 0f128d4d-3cf9-46de-bb31-ed159450d6cf

Pacote RAW 16B: A5 01 | seq:u16 | window:u16 | ms:u32 | red:u24 | ir:u24.
Pacote G1 12B:  A5 02 | window:u16 | end_ms:u32 | pass:u8 | reason:u8 | count:u16.
Todos os campos inteiros little-endian. Compatível com MTU padrao de 23B.

## Testes em bancada
1. Revisar pinagem, instalar biblioteca e compilar no Arduino IDE.
2. Conectar via cabo USB (115200), enviar e, r. Verificar echop, pressao numerica,
   linhas R e um Q a cada 5 segundos. Usar pitaco24_ppg_probe.py para CSV.
3. Sem dedo: G1 FAIL; dedo estavel: esperar G1 PASS caso thresholds sirvam na montagem.
4. Executar c e z; confirmar que pressao permanece funcional e que perda de
   FIFO nao passa falsamente por janela valida.
5. BLE: confirmar pressao na caracteristica original e RAW+G1 na nova.
6. Comparar contador seq entre USB/BLE e contagens por janela; testar carga simultanea.

## Limitacoes tecnicas atuais
- G1 thresholds empiricos, NAO clinicos.
- A biblioteca SparkFun tem buffer interno pequeno e ainda precisa ser testada
  sob concorrencia de notificacoes BLE, calibracao e coleta continua.
- Calibrate() do PITACO original ainda tem bloqueio; janelas com poll longo
  sao marcadas como suspeitas, mas isso NAO detecta todas as perdas de FIFO.
- Ainda NAO compilado em hardware nem verificado com dispositivo/Unity.
- Nao existe treinamento ML-Agents nem estimativa validada de FC/SpO2 nesta branch.
- Nova telemetria serial USB exige parser diferenciado na ponte Python, a ser
  integrado no proximo nivel; cliente legado pode ignorar as linhas nao numericas.

Teste host, na pasta do sketch:
g++ -std=c++11 -Wall -Wextra -Werror -I. sqi_gate1.cpp tests/test_sqi_gate1.cpp -o /tmp/pitaco_g1 && /tmp/pitaco_g1

Fontes: RFC sqi_flow_v5_baseline/gate_01_integrity.ino;
RFC DECISAO_TECNICA_ARMAZENAMENTO_18BIT_E_VALIDACAO_G1.md;
RFC spo2-wrist-sensor/main/processing/sqi/gates/g1_integrity/.
