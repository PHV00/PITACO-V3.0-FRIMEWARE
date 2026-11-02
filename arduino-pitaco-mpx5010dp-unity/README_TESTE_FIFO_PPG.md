# PITACO 2.4 — Estados STOPPED/COLLECTING e recuperacao da FIFO

## Evidencia experimental (logs de bancada de 02/11/2026)

No firmware anterior, coletor USB `pitaco24_ppg_probe.py` obteve somente
pressao; G1 retornou `reason=1,samples=0` durante sete janelas.
Leitura direta de registros mostrou repetidamente:

```text
X,PPG_REG,part=15,mode=03,fifoCfg=4F,adcCfg=27,ledR=1F,ledIR=1F,wr=0,rd=0,ovf=31,novas=0,buffer=0
```

`ovf=31` e consistente com overflow saturado. `wr=rd` nao permite
distinguir FIFO cheia de FIFO vazia apenas pelos ponteiros. O sistema
respondia a I2C, os LEDs e o modo RED/IR estavam configurados. Nao ha
ainda comprovacao experimental da origem exclusiva do overflow.

## Politica nova

```text
BOOT -> MAX30105.setup -> shutDown -> STOPPED
STOPPED -- r + calibrado + sem zero/OTA --> wakeUp -> clearFIFO -> COLLECTING
COLLECTING -- f / e / zero / OTA --> shutDown -> STOPPED
COLLECTING -- overflow --> G1 GAP -> consumir amostras acessiveis
                              -> clearFIFO (recuperacao) -> COLLECTING
```

- Sem amostras no estado parado: **nao se chama `check()` enquanto parado**.
- `clearFIFO()` na transicao para COLLECTING remove dados antigos de
  quando o sensor estava desligado; nao e descarte periodico.
- Enquanto coletando, os pares sao encaminhados a `g1Add()`, detecao
  experimental de BPM e JSON USB/BLE antes de `nextSample()`.
- Em overflow: perda ja aconteceu, portanto G1 marca `reason=9 (GAP)`.
  A tentativa de consumir amostras ainda acessiveis precede a limpeza.
- A biblioteca SparkFun emprega buffer de software com 4 posicoes,
  distinto da FIFO fisica de 32 registros. Se a contagem de `check()`
  superar `available()`, o firmware registra `PPG_SW_RING_OVERRUN`
  e reprova a janela. A prevencao requer atendimento frequente da FIFO.

## Validacao passo a passo (Arduino IDE e Windows PowerShell)

1. Conferir a branch `feature/pitaco-24-simple-json-usb-ble-bpm` e
   sincronizar o repositorio com `git pull --ff-only`.
2. Gravar o sketch principal com o arquivo `gate_01_integrity.ino`
   na mesma pasta. Placa ESP32-C3, SparkFun MAX3010x instalada,
   USB CDC On Boot conforme hardware, 115200 baud.
3. Abrir Monitor Serial, sem comecar a coleta. Verificar
   `X,MAX30105_READY,RED_IR` e `X,PPG_STATE,STOPPED`. Aguardar
   10 segundos **sem pressionar r**. Nao deve haver G1 nem amostras PPG.
4. Com o circuito respiratorio em repouso, enviar `z` se for
   necessario calibrar pressao; aguardar `zero_done`. O PPG fica parado.
5. Enviar `r`. Verificar `X,PPG_STATE,COLLECTING`,
   `type:sample` com RED/IR e `X,PPG_DIAG` exibindo
   `processadas>0`. Esperado ~25 pares/s, sujeito a carga real.
6. Em 5 segundos, verificar `type:g1`: para dedo estavel deve ser
   possivel obter `samples>0`; PASS nao e garantido antes de recalibrar
   thresholds para o MAX30105 real.
7. Enviar `f`: verificar `X,PPG_STATE,STOPPED`. Aguardar 5 segundos
   e confirmar ausencia de mensagens `sample` e `g1`.
8. Enviar `r` novamente. Deve retomar RED/IR e reiniciar a janela,
   sem necessitar religar a placa.
9. Fechar Monitor Serial e executar:
   `python .\\pitaco24_ppg_probe.py COM3 --seconds 35 --csv fifo_teste.csv`.
   Nunca abrir COM3 no Arduino IDE e Python simultaneamente.
10. Repetir com dedo estavel, sem dedo, fluxo respiratorio e conexao
    BLE ativa. Monitorar `X,PPG_FIFO_OVERFLOW`,
    `X,PPG_SW_RING_OVERRUN`, G1=GAP e saltos de seq.

## Criterios de aceite para a proxima iteracao

- Aguardar 10+ segundos em STOPPED nao provoca interrupcao da
  primeira coleta. Nao ha dados antigos na primeira janela.
- Em COLLECTING aparecem amostras RED e IR e janelas G1 com
  `samples>0`.
- Sem perdas observadas, `ovf=0` e contagem de processadas
  aproximadamente igual a novas ao longo de alguns minutos.
- Ao interromper e recomecar a sessao, a pressao legada continua
  disponivel e BLE/OTA continuam compativeis.
- Havendo perda/overflow, o G1 nao apresenta falso PASS.

**Estado de verificacao:** implementacao pronta para ensaio; o hardware
fisico e a compatibilidade BLE/Unity ainda precisam ser comprovados.
BPM e SpO2 nao sao clinicamente validados; SpO2 segue indisponivel.

Referencia de software: https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library
