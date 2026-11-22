# Marco 03 — Consolidação do firmware PPG/SQI PITACO 2.4

**Data:** 22/11/2026  
**Repositório:** `PHV00/PITACO_ESP32`  
**Branch de trabalho:** `test/ppg-g1-redflat-350`  
**Destino aprovado pelo mantenedor:** `main`  
**Integração correspondente:** `PHV00/iblueit-psychophysiological-flow-pitaco2.4-port`, Marco 03, PR de consolidação #13.  
**Natureza:** marco de desenvolvimento de bancada; NÃO é validação clínica, calibração de oxímetro ou comprovação de que o binário foi gravado no ESP32.

## 1. Contexto e delimitação

O PITACO 2.4 transmite via USB amostras PPG RED/IR adquiridas no MAX3010x, o resultado do Gate 01 (G1) de integridade e estados de contato. O jogo I Blue It 5.0, em repositório distinto, recebe JSON, aplica sua janela de processamento de ~8 s, calcula BPM por autocorrelação IR, SpO₂ DEMO experimental por RED/IR, decide a apresentação no HUD e envia medições elegíveis ao Mixer.

Neste repositório, a consolidação do Marco 03 tem **escopo pequeno e explícito**: separar limiares de amplitude RED e IR no firmware e manter documentada a evidência/limitação do teste. As melhorias de fila serial, relógio monotônico, HUD 60 s, Deep DDA e integração com Mixer pertencem **ao repositório Unity**, não a este firmware.

A comparação desta branch com a `main` inicial de firmware `35e0c0ca4b3c2a3249e68bcf1db8d9ddc0e49b2f` mostrou **1 commit, 1 arquivo de código alterado (+5/−3 linhas)** antes da documentação de fechamento.

## 2. Alteração consolidada

**Arquivo:** `frimeware2.4/sqi/gate_01_integrity.ino`.

Antes, o G1 utilizava um limiar único de pico-a-pico bruto:

```cpp
static const uint32_t G1_MIN_RANGE = 500UL; // RED e IR
```

Neste experimento passa a utilizar:

```cpp
static const uint32_t G1_MIN_RED_RANGE = 350UL; // experimental
static const uint32_t G1_MIN_IR_RANGE = 500UL;  // baseline preservado
```

Decisões:

```cpp
else if (g1RedMax - g1RedMin < G1_MIN_RED_RANGE) *reason = 4; // RED_FLAT
else if (g1IrMax - g1IrMin < G1_MIN_IR_RANGE)   *reason = 5; // IR_FLAT
```

A verificação mantém a precedência de `GAP`, amostras mínimas, médias baixas e os critérios de clipping já existentes. `reason=4` ainda pode reprovar integralmente o G1, e a Unity atualmente invalida sua janela C# de ambos os canais quando recebe FAIL G1. Este commit **não** implementa elegibilidade separada de BPM e SpO₂, nem muda estimadores, valores de LED, taxa de amostragem ou interface BLE.

### Por que é experimental

- O `range=max-min` da janela RED/IR é medida de variação bruta, **não** índice suficiente de periodicidade, morfologia ou acurácia.
- O limiar foi herdado de protótipos de bancada e requer caracterização do sensor e montagem reais.
- **350 não foi demonstrado como limite ótimo**. Para comprovar sua utilidade, registrar janelas com amplitude RED entre 350 e 499 e verificar que passam pelo G1 do firmware gravado; confrontar a utilidade do sinal com métricas independentes.
- O diagnóstico `UNITY_RAW_SHADOW_NOT_FIRMWARE` exibe amplitude de janela própria da Unity, sem garantir identidade exata com a janela do ESP32; `refMinRange=500` da Unity não informa o limiar do binário efetivamente gravado.
- Fazer merge de código na GitHub `main` **não grava o hardware**. A placa deve ser compilada/flasheada e sua versão identificada separadamente.

## 3. Evidência do ciclo do Marco 03 (correlação com Unity)

O último log de bancada (22/11/2026, `Texto colado(20261122-152016).txt`, mantido fora do repositório) foi realizado **após ajuste relatado dos cabos**. A Unity registrou até t=194,92 s:

| Métrica | Observado | Significado limitado |
| --- | --- | --- |
| G1 firmware observado na Unity | 30 PASS / 34 janelas | 3 FAIL motivo 2 no período sem dedo; 1 FAIL motivo 4 com contato |
| BPM Unity | 315/338 tentativas publicadas | 93,2% de decisões de cálculo, não precisão nem cobertura temporal |
| Serial Unity | `serialDropped=0`, `invalidJson=0`, `invalidSample=0` | Sem perdas nessas categorias |
| Continuidade | `clockSampleGaps=0`, `clockRestarts=0`, `contactLossConfirmed=0` | Nenhum desses eventos confirmado no trecho |
| G1 em t=74,33s | `reason=4`, shadow `redRange=484`, `irRange=1159`, `contact=True` | Evento RED_FLAT importante; não comprova limiar executado |
| HUD Unity | mostra BPM/O₂ atuais e médias móveis até 60 s | Mudança implementada **no outro repositório** |
| Tempo Unity | stall de 4,70 s, sem descartes da fila | Limitação da cena/host, não diagnóstico direto de hardware |

A maior estabilidade após ajuste de cabos é compatível com contribuição da montagem e do acoplamento óptico; **não** prova causalidade exclusiva. O registro da sessão não permite identificar commit/binário do firmware gravado nem estabelecer se o 350 alterou uma decisão G1.

## 4. Contrato de integração e próximos estudos

```text
MAX3010x RED/IR → firmware PITACO 2.4
 ├─ amostras e tempo do dispositivo/seq
 ├─ contato óptico (independente)
 └─ G1: médias, amplitude RED=350 experimental, IR=500, clipping, gap
      |
      v
USB / JSON existente
      |
      v
Unity / I Blue It 5.0
 ├─ G1 + contato + janela de 8 s
 ├─ BPM IR + SpO₂ RED/IR DEMO
 ├─ HUD atual/média 60 s
 └─ Bridge → Mixer → recompensas experimentais para DeepDDA
```

**Pendências deliberadamente adiadas ao ciclo seguinte:**

1. Expor versão/commit e constantes do G1 na telemetria de startup para rastrear o firmware físico.
2. Repetir captação RAW sob montagem/cabos/pressão/temperatura controlados; usar referência fisiológica para BPM e calibração apropriada se houver estudo de SpO₂.
3. Comparar decisões 500 versus 350 **nos mesmos dados brutos**; confirmar retorno de `reason=4` no mesmo intervalo temporal e janelas equivalentes.
4. Separar qualidade/aptidão do IR para BPM e RED+IR para SpO₂ sem banalizar falhas reais de integridade.
5. Revisar estratégia de reset Unity para que uma falha RED com IR útil não apague todo histórico de modo desnecessário.
6. Testar processamento baseline simples vs SQI em paralelo (sem enviar valores não aprovados a alertas).
7. Diferenciar dispositivo de referência MAX30102/MAX30105 e validar parâmetros de aquisição reais no hardware.
8. Não atribuir valores SpO₂ DEMO a saturação sanguínea real; uso apenas experimental.

## 5. Rastreabilidade, verificação e fechamento

- Commit de implementação: `cf9f910f3182df28859daccdd8cce2afc4c2d122` — `test(ppg): lower G1 RED_FLAT range to 350; keep IR at 500`.
- Diff de implementação revisado pelo GitHub; nenhuma outra rotina de G1 foi alterada nessa branch.
- **Não há** evidência nesta consolidação de compilação Arduino, flashing do ESP32, calibração do MAX3010x ou teste fisiológico sincronizado.
- Documentação correspondente na Unity: `docs/marcos/CONSOLIDACAO_PITACO24_UNITY_PPG_DEEPDDA_HUD_2026-11-22.md` (na branch/PR da Unity).

**Status do Marco 03:** fechado para **integração do código experimental ao ciclo principal e documentação cruzada** mediante decisão do mantenedor; não fechado para acurácia, segurança clínica ou validação do limiar. O próximo desenvolvimento ocorrerá em etapa/branch distinta, sem reescrever a rastreabilidade deste marco.
