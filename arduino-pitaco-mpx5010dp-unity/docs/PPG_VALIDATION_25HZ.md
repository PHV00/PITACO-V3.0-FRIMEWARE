# PITACO 2.4 — Validação offline de PPG e BPM a ~25 Hz

> **Estado: pesquisa exploratoria; NAO e uma calibracao clinica.**
> A rotina deste documento somente le CSV e gera um relatorio. Nao altera o
> firmware, `G1_MIN_RANGE=500`, Gate 01, GUI, BLE/USB, Unity nem DeepDDA.
> Nao use BPM/SpO2 experimentais para seguranca do paciente.

## Motivacao

O MAX30102 e configurado no firmware com taxa nominal de 100 amostras/s
e media FIFO de 4, resultando em aproximadamente **25 pares RED/IR/s**
(40 ms/par). A correcao FIFO64 foi validada no USB em bancada, mas a
amplitude RED diminuiu durante o ensaio. O Gate 01 atual decide
`RED_FLAT`/ `IR_FLAT` por `max-min < 500` em cada janela de ~5 s.
Esse criterio **pode aprovar deriva lenta** sem comprovar ciclos pulsateis.

## Arquitetura da analise — sem efeitos colaterais

```text
CSV bruto, type=sample + type=g1
               |
       leitura / validacao
               |
    +----------+---------------------+
    |                                |
 janelas G1 reais                 periodo de 8 s
 (samples informado)              G1+contato efetivos
    |                                |
 RED/IR media, range              analizador Python
 deriva linear e ponta-a-ponta    EXPERIMENTAL existente
 AC RMS / DC                      estima BPM ou razao rejeicao
    |                                |
 varredura 300..1000 ADC            contagem de disponibilidade
 com/sem labels externos           (NAO acuracia)
    |                                |
    +-------------+------------------+
                  |
       relatorio JSON auditavel
```

**Fontes de implementacao:** `gate_01_integrity.ino`,
`pitaco_bridge/experimental.py`,
`src/vendor_sparkfun_max3010x/heartRate.cpp`.
A funcao `sparkfun_fir_gain()` reproduz a **resposta em frequencia do
FIR de 23 taps** do arquivo SparkFun, NAO o detector completo
(`averageDCEstimator` + zero crossing + limiares).

## Executar — PowerShell na raiz do repositorio

```powershell
cd arduino-pitaco-mpx5010dp-unity
python .\pitaco_experimental\analyze_ppg_25hz.py .\ppg_fifo64_60s.csv --output .\ppg_25hz_report.json
python -m unittest discover -s tests -p "test_*.py"
```

A captura deve ter colunas `type,seq,t_ms,red,ir,bpm_valid,g1,reason,samples,contact`.
Aceita CSV gerado pelo probe ou GUI. As linhas `type=pressure` sao
ignoradas. O algoritmo utiliza o evento `type=g1` e seu
`samples` para selecionar as amostras relevantes de cada janela;
a validacao `complete` exige quantidade de registros correta,
sequencia `seq` continua (considerando wrap uint16) e deltas temporais
positivos de ate 100 ms. `seq_contiguous` e `timing_ok` sao expostos
separadamente no JSON. Um evento de contato ausente reinicia o
acumulador offline.
O resultado e descritivo: **nenhum limiar novo e aplicado no dispositivo**.

## O que significam as colunas

| Coluna | Interpretacao | Limite |
| --- | --- | --- |
| `red_range`, `ir_range` | Pico a pico bruto, max-min, contagens ADC | Sensivel a movimento/deriva |
| `*_endpoint_change` | Valor final menos inicial | Pode incluir pulsos |
| `*_linear_trend` | Deriva aproximada por regressao linear em 5s | Nao equivale a remover todos os artefatos |
| `*_ac_rms` | RMS do sinal residual apos media movel e suavizacao | Medida exploratoria, nao referencia clinica |
| `*_ac_dc` | RMS residual dividido pela media DC | Nao e indice de perfusao calibrado |
| `threshold_sweep` | Quantas janelas passariam no **criterio de range RED e IR** | Nao reexecuta todos os gates |
| `experimental_8s_windows` | Tentativas do analisador Python com G1 e contato validos | Nao mede sensibilidade clinica |
| `sparkfun_fir_gain` | Modulo do FIR SparkFun por BPM e taxa de amostragem | Nao equivale a probabilidade de detectar beat |
| `sparkfun_pba_replay` | Reexecucao aproximada do PBA SparkFun IR >> 3 com estado e filtro FIR | Nao substitui verificacao no ESP32; intervalos RR devem ser confirmados |

Valores AC e tendencias **nao comprovam pulsacao sem uma referencia
independente**, especialmente na presenca de movimento.

## Evidencia inicial observada — CSV USB de 04/11/2026

Captura de 1.498 samples (~60 s), 11 janelas G1, 8 PASS e 3
`RED_FLAT` (reason=4). Sem BPM firmware valido. Nas janelas G1
9–11 os ranges RED eram 422, 442 e 380 ADC, respectivamente.
A janela 8 passou no G1 com range RED=991 ADC, mas a mudanca
inicio/fim foi de -986 ADC: evidencia de forte componente lenta
potencialmente confundindo a decisao por faixa bruta.
**Nao e evidencia de que reduzir 500 seja correto.**

No replay do mesmo CSV pelo analisador **experimental ja existente**
com G1 e contato validos, houve 33 avaliacoes de 8 s e BPM disponivel
em apenas 6 delas. Esses seis numeros **nao foram comparados com uma
referencia independente** e nao constituem acuracia nem autorizacao
para uso no jogo.

O ganho teorico do FIR original, calculado de seus coeficientes:
- 25 Hz: 60 BPM ~0,774; 90 BPM ~0,318; 120 BPM ~0,063;
- 100 Hz: 60 BPM ~1,396; 90 BPM ~1,332; 120 BPM ~1,246.

A resposta total de `checkForBeat` tambem depende do estimador DC,
`ir >> 3`, estado interno e do limiar de amplitude 20..1000.

O replay offline da logica inteira do `heartRate.cpp` da captura USB
observou **8 eventos** de beat, mas **0 pares de eventos consecutivos**
no intervalo de 300..1714 ms aceito pelo firmware para gerar BPM.
Isso e consistente com a ausencia de BPM no CSV, mas deve ser confirmado
com logs de timestamps de batimentos na placa. Em senoide artificial
IR com amplitude de 1000 ADC, 120 BPM, 30 s: o replay detecta zero
batimentos a 25 Hz e detecta eventos a 100 Hz. Nao extrapolar isso
para sujeitos reais ou para todas as amplitudes.

O replay `sparkfun_pba_replay.py` e **um comparador de bancada**:
transcreve as operacoes inteiras, filtros e limiares da biblioteca,
mas nao testa as interrupcoes, deriva de tempo, I2C ou estado real do ESP32.

## Como escolher um limite com referencia

1. Capturar condicoes controladas: dedo estabilizado, pressao de
   contato variada, movimento, contato ausente e reposicionamento.
   Registrar o contexto real de cada janela em planilha externa.
2. Obter **rotulos independentes** de utilidade pulsatoria (0/1)
   por inspeção de ondas e, para BPM, referencia simultanea (ECG
   ou dispositivo validado). Evitar definir o rotulo usando o proprio
   G1, pois isso seria validacao circular.
3. Criar CSV externo com colunas `window,usable` e executar:
   ```powershell
   python .\pitaco_experimental\analyze_ppg_25hz.py .\ppg_fifo64_60s.csv --labels .\labels_ppg.csv --output .\relatorio.json
   ```
4. Examinar TP/FP/FN/TN, sensibilidade e especificidade **somente
   para o criterio de range RED+IR**. Repetir em participantes e
   sessoes independentes; comparar alternativas com AC/DC e
   periodicidade, nao apenas variar um cutoff bruto.
5. Fixar thresholds em treino e medir generalizacao em ensaio
   **separado**. Nao alterar o G1 atual sem documentar casos que
   melhoram/pioram, preservar testes de contato e saturacao.

CSV bruto e rotulos de participante **nao devem ser commitados** no
repositorio. A suite host exercita apenas sinais artificiais.
O ambiente Python experimental nao calibra SpO2 e seus resultados
nao sao transmitidos para Unity ou DeepDDA.

## Proxima implementacao, apos dados rotulados

- Comparar em replay do mesmo CSV o detector `checkForBeat()` em
  25 Hz versus um estimador com configuracao adequada ao fs, sem
  simplesmente abaixar os limites de amplitude.
- Separar SQI de integridade (G1) de SQI pulsatorio (gate futuro),
  definindo rotulos e parametros configuraveis.
- Testar com BLE + GUI em carga e confirmar que o ganho de qualidade
  nao compromete a aquisicao nem a respiracao.
