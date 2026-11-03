# PITACO 2.4 — Estados STOPPED/COLLECTING e recuperacao da FIFO

## Evidencia experimental (logs de bancada de 02/11/2026)

Em teste posterior, a limpeza enquanto o sensor permanecia ativo retornou
`antes=31,depois=31`, repetidamente. Um diagnostico com `shutDown()`
retornou `modo=83,ackOvf=0,ovf=0,ackLed=0,ledAntes=1F,ledTeste=00`,
confirmando que houve sucesso na escrita I2C e no zeramento da FIFO
com o sensor parado. Isso motiva a mudanca da sequencia, ainda nao
validada em aquisicao continua.

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

## Validacao USB com MAX30105 real — 02/11/2026 (confirmada)

Apos o commit `4ea1951`, ensaio de bancada com ESP32-C3 e
`python .\\pitaco24_ppg_probe.py COM3 --seconds 35`:

```text
X,PPG_PRESTART,ovf=0,wr=0,rd=0
X,PPG_SENSOR_AWAKE,mode=03
X,PPG_STATE,COLLECTING
X,PPG_DIAG,novas=50,processadas=50,wr=18,rd=18,ovf=0
G1 1 {'g1': True, 'reason': 0, 'samples': 125}
G1 2 {'g1': True, 'reason': 0, 'samples': 124}
G1 3 {'g1': True, 'reason': 0, 'samples': 125}
G1 4 {'g1': True, 'reason': 0, 'samples': 125}
G1 5 {'g1': True, 'reason': 0, 'samples': 125}
G1 6 {'g1': False, 'reason': 2, 'samples': 125}
Amostras PPG 874 janelas G1 6 saltos de sequencia 0
```

Resultados observados:
- **Aquisicao RED/IR restabelecida**: 874 pares em 35 s
  (media ~24,97 pares/s), proxima dos 25 Hz esperados.
- **FIFO acompanhada**: diagnosticos em ~2 s mostraram normalmente
  `novas=50,processadas=50,ovf=0`; um ciclo registrou 49/49.
  O instante `wr=16,rd=15,ovf=0` indica um registro pendente,
  nao overflow. Nao houve evento de overflow no log fornecido.
- **Integridade de transporte USB**: zero saltos de sequencia
  na janela de 35 s. Isto nao valida throughput sob BLE/Unity.
- **G1 em 5 s**: cinco janelas PASS (reason 0) e uma RED_LOW
  (reason 2); todas receberam 124 ou 125 amostras.
  RED_LOW indica media RED abaixo do limiar provisiorio de 5000,
  sem evidencia suficiente para atribuir causa optica especifica.
- **Limites da conclusao**: ausencia de valores individuais RED/IR/BPM
  no log de status compartilhado impede verificar amplitude real do
  pulso, acuracia de BPM ou comportamento sem dedo/movimento.
  A correcao do ciclo STOPPED->COLLECTING esta validada para este
  ensaio curto em USB, nao ainda para uso continuo, OTA ou BLE.

Proximos ensaios: analisar o CSV com RED, IR, BPM, `bpm_valid`, timestamps
e SQI; repetir com dedo firme, dedo removido e movimento controlado.
Depois testar `f`/`r` em sequencia, ciclo `z`, sessao prolongada
(2-5 min) e BLE ativo, verificando overflow e sequencias. Nao alterar
os thresholds G1 sem observar distribuicao de RED/IR e evidencias.

## Validacao USB com protocolo de contato — 60 s (02/11/2026)

Ensaio com `python .\\pitaco24_ppg_probe.py COM3 --seconds 60 --csv ppg_contato_60s.csv`.
O relatorio abaixo e baseado no log de status e G1 fornecido em conversa;
o CSV com RED/IR/BPM ainda nao foi disponibilizado para analise.

```text
X,PPG_PRESTART,ovf=0,wr=0,rd=0
X,PPG_SENSOR_AWAKE,mode=03
X,PPG_STATE,COLLECTING
G1 1  PASS      samples=125
G1 2  PASS      samples=124
G1 3  PASS      samples=125
G1 4  PASS      samples=125
G1 5  RED_LOW   samples=125
G1 6  RED_LOW   samples=125
G1 7  PASS      samples=125
G1 8  PASS      samples=125
G1 9  IR_FLAT   samples=125
G1 10 PASS      samples=125
G1 11 PASS      samples=125
Amostras PPG 1498 janelas G1 11 saltos de sequencia 0
```

Observacoes:
- 1498 pares/60 s = ~24,97 Hz, proximo dos 25 Hz efetivos esperados.
- Todos os logs periodicos de FIFO apresentaram `ovf=0`; contagens de
  `novas` e `processadas` foram equivalentes (49 ou 50 por 2 s).
- Zero gaps de seq no monitor USB; nao se deve estender esta conclusao
  ao transporte BLE sem teste proprio.
- 8/11 janelas G1 PASS, duas `reason=2` (RED_LOW) e uma `reason=5`
  (IR_FLAT). Todas as janelas continham 124 ou 125 registros.
- Se o protocolo de fases de 15 s (dedo, sem dedo, dedo, movimento)
  foi seguido pontualmente, a janela 4 PASS coincide aproximadamente
  com a fase sem dedo; isto sugere **falso PASS ou latencia de deteccao**,
  nao uma conclusao definitiva sem amostras brutas e marcadores reais.
- A janela 9 IR_FLAT recai aproximadamente na fase de recolocacao
  quando usamos as fases planejadas; nao atribuir automaticamente a movimento.
- No Gate 01 atual, `g1Evaluate()` usa media dos canais e amplitude
  min/max por 5 s; nao existe detector especifico de contato.
  Uma janela PASS nao comprova pulsatilidade ou contato anatomico adequado.

**Decisao:** preservar firmware, thresholds G1 e maquina STOPPED/COLLECTING
nesta iteracao. Solicitar `ppg_contato_60s.csv`, analisar canais,
BPM, variacao, timestamps e as transicoes de cada fase antes de implementar
um mecanismo rapido de presenca de dedo ou alterar o Gate 01.

## Leitura dos dados brutos e ajuste de contato (02/11/2026)

O CSV enviado mostra queda do RED/IR em ~15,53 s (RED ~34.017,
IR ~35.824) depois de valores ~102 mil/~113 mil. Em ~16,09 s,
os dois canais estavam abaixo de 3 mil; o platô sem dedo foi
~1.400 RED/~1.100 IR até ~31,14 s. O retorno ocorre em ~31,2 s
com subida acima de 90 mil nos dois canais.

A janela G1 4 foi PASS mesmo contendo varios segundos sem dedo:
a alta media inicial e o grande intervalo min/max da transicao
enganam os thresholds estatisticos de cinco segundos.
BPM e bpm_valid foram nulo/falso em todo o CSV apresentado.

### Precondicao de contato (experimental)

- Um par RED/IR opticamente apto exige ambos >=5000 e sem clipping.
  Este criterio, baseado na grande separacao observada em bancada,
  **nao e validador clinico de contato ou de PPG fisiologico**.
- Sao necessarias 3 amostras consecutivas (~120 ms a 25 Hz depois da
  travessia do limiar) para confirmar PRESENCA ou AUSENCIA.
- Enquanto o contato instantaneo nao for apto, o JSON de sample
  informa \`sqi.contact=false\`, \`sqi.g1=false\`, \`reason=10\`.
  Assim nao se reutiliza PASS de uma janela antiga apos finger-off.
- O status \`X,PPG_CONTACT,PRESENT\` ou \`X,PPG_CONTACT,ABSENT\`
  confirma transicoes. O G1 e reiniciado ao mudar o estado de contato
  para impedir que uma janela mista seja reutilizada como valida.
- Os valores RAW sao SEMPRE enviados, inclusive sem dedo, para
  auditoria. O calculo BPM exige contato confirmado e sample apto.
- O diagnostico agora inclui \`beats=\` (deteccoes de checkForBeat
  por intervalo de 2 segundos) e \`contact=\` (estado confirmado).
  Isso ajudara a investigar o BPM que permaneceu ausente no CSV.
- A ponte Python preserva as colunas antigas e acrescenta \`contact\`.

**Pendencias:** verificar os novos campos em ESP32-C3, repetir os
quatro estados com dedo, sem dedo, recolocacao e movimento; ajustar
limiares com distribuicoes de varias coletas e validar BPM isolado.

## Politica nova

```text
BOOT -> MAX30105.setup -> shutDown -> STOPPED
STOPPED -- r + calibrado + sem zero/OTA --> clearFIFO -> verificar -> wakeUp -> COLLECTING
COLLECTING -- f / e / zero / OTA --> shutDown -> STOPPED
COLLECTING -- overflow --> G1 GAP -> consumir amostras acessiveis
                              -> shutDown -> clearFIFO -> verificar -> wakeUp -> COLLECTING
```

- Sem amostras no estado parado: **nao se chama `check()` enquanto parado**.
- `clearFIFO()` na transicao para COLLECTING remove dados antigos de
  quando o sensor estava desligado; e executado **antes de wakeUp()**.
  O firmware verifica imediatamente OVF/WR/RD; se nao zerarem, desliga
  apenas PPG e registra `X,PPG_ERROR,PRESTART_RESET_FAILED`.
- O modo de operacao apos `wakeUp()` tambem e lido e registrado.
  `X,PPG_PRESTART` e `X,PPG_SENSOR_AWAKE` facilitam o diagnostico.
- Enquanto coletando, os pares sao encaminhados a `g1Add()`, detecao
  experimental de BPM e JSON USB/BLE antes de `nextSample()`.
- Em overflow: perda ja aconteceu, portanto G1 marca GAP e bloqueia
  temporariamente BPM. A tentativa de consumir amostras ainda acessiveis
  precede a recuperacao `shutDown -> clearFIFO -> readback -> wakeUp`.
  Somente se OVF/WR/RD zerarem emitimos `X,PPG_FIFO_RECOVERED`.
  Caso contrario, `X,PPG_ERROR,FIFO_RESET_FAILED` desliga apenas o PPG,
  evitando um ciclo infinito de mensagens, mas preserva a pressao.
  Sem nenhuma amostra na janela, G1 reportara `NO_SAMPLES` (reason 1),
  mesmo que tenha sido marcado um GAP; diagnosticos de erro complementam
  esse resultado.
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
5. Enviar `r`. Verificar `X,PPG_PRESTART,ovf=0,wr=0,rd=0`,
   `X,PPG_SENSOR_AWAKE,mode=03` (bits relevantes), e depois
   `X,PPG_STATE,COLLECTING`. Observar `type:sample` com RED/IR e
   `X,PPG_DIAG` exibindo `processadas>0` (~25 pares/s esperados).
   Se ocorrer `X,PPG_ERROR,*`, parar o ensaio e enviar o log completo;
   nao forcar a recuperacao manual repetidamente.
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

**Estado de verificacao:** aquisicao RED/IR via USB confirmada em
bancada por 35 segundos (874 pares, zero overflow/seq gaps observados,
5/6 janelas G1 PASS); testes prolongados, BLE/Unity, qualidade de PPG
sob movimento e acuracia BPM permanecem pendentes.
BPM e SpO2 nao sao clinicamente validados; SpO2 segue indisponivel.

Referencia de software: https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library
