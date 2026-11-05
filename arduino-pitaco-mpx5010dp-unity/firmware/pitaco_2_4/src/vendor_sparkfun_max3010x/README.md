# Driver SparkFun local para o PITACO 2.4

Esta pasta contem uma copia localizada da biblioteca SparkFun MAX3010x, para que
as correcoes de FIFO sejam reproduziveis em diferentes instalacoes da Arduino IDE.
**Nao alterar a biblioteca SparkFun global instalada no computador.**

Fonte: https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library
Arquivos originais (`master` ao integrar):
- `src/MAX30105.h`: blob Git 0dcace766d45b66aef6ce62cd79d5a78e932e67b
- `src/MAX30105.cpp`: blob Git f2a9d43b13af2bb091850115aabfcb4c23d2d35c
- `src/heartRate.h`: blob Git 42ecca21b41a8dcbdd9b2943c11fa3ba6fbf3516
- `src/heartRate.cpp`: blob Git 92820ec6bec0c3f63dc66e63e1e1713109710546

Mudancas PITACO em `MAX30105.h/.cpp`:
1. `STORAGE_SIZE`: 4 -> 64 (63 slots utilizaveis; um diferencia cheio/vazio).
   Memoria dos tres canais: 768 bytes, em vez de 48 bytes.
2. `check()`: consulta a ocupacao do anel e limita a leitura ao numero de
   slots livres; as transferencias I2C sao divididas em blocos de registros
   completos, sem usar bytes de leituras incompletas. Retorna apenas a
   quantidade realmente inserida.
3. `takeFIFOReadError()`: informa uma leitura I2C incompleta ou erro de
   transacao. O orquestrador marca lacuna G1 e ressincroniza a FIFO fisica.
4. `clearFIFO()`: limpa ponteiros no sensor **e** no anel em RAM, evitando
   transportar amostras da sessao anterior apos stop/restart/overflow.
5. `heartRate.*`: mantidos **sem alteracoes**. O BPM experimental continua
   com a mesma implementacao.

O limite fisico do MAX30102/MAX30105 e 32 registros na FIFO do sensor.
Ampliar o anel do ESP32 nao evita overflow se a CPU/USB/BLE ficar tempo demais
sem esvaziar a FIFO. O codigo preserva `ovf`, `PPG_FIFO_OVERFLOW`,
`PPG_SW_RING_OVERRUN`, `PPG_I2C_FIFO_READ_ERROR` e a causa G1=9.

Compilacao: abrir `firmware/pitaco_2_4/pitaco_2_4.ino` na Arduino IDE com
placa ESP32-C3 configurada. A pasta `src/` do sketch e compilada
recursivamente pelo Arduino. Os includes especificos da pasta local evitam
compilar uma segunda copia externa do driver. Nenhum UUID, payload JSONL,
comando de pressao, OTA ou regra G1 foi alterado nesta mudanca.

Validacao necessaria no hardware:
- 60 s com contato estavel, 25 amostras/s, `ovf=0`, sem erro I2C e
  `novas=processadas`;
- repetir com BLE conectado, observar as perdas de sequencia no Python;
- ensaiar backlog controlado e parada/reinicio para confirmar que nao ha
  amostras antigas nem falsos G1 PASS;
- verificar compilacao Arduino/ESP32-C3 e BPM experimental (nao clinico).

Licencas preservadas em `LICENSE.md`, `MAX30105.*` e `heartRate.*`.
