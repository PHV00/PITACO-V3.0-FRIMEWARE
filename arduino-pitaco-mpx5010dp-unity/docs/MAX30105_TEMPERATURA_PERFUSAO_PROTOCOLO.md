# PITACO — Protocolo exploratório de temperatura, perfusão periférica e qualidade do PPG (MAX30105)

**Estado:** proposta documental para revisão; sem implementação neste PR.  
**Equipamento:** PITACO ESP32-C3 com sensor óptico **MAX30105** da Analog Devices/Maxim, conectado por I²C e integrado à biblioteca SparkFun MAX3010x.  
**Natureza:** estudo exploratório de bancada; **não é validação clínica de SpO₂, frequência cardíaca ou perfusão**.

## 1. Contexto e observação inicial

Durante um teste informal com outra participante, o monitor PPG do PITACO apresentou dificuldade para identificar pulsos no dedo até que ele fosse aquecido. Após aquecimento confortável, a aquisição pareceu melhorar. Essa observação é **anedótica e ainda não foi quantificada**; não demonstra, por si só, causalidade, nem identifica pigmentação como causa.

### Hipóteses de trabalho, em ordem inicial de investigação

- **H1 — Perfusão/temperatura:** dedos frios podem apresentar vasoconstrição periférica e menor modulação pulsátil detectável; o aquecimento confortável pode aumentar a amplitude AC do PPG.
- **H2 — Acoplamento e geometria óptica:** pressão de contato, posição do dedo, movimento, luz ambiente, cobertura do módulo, distância da superfície e características dos tecidos podem alterar os níveis RED/IR e a modulação.
- **H3 — Pigmentação da pele:** a absorção óptica relacionada à melanina pode influenciar a resposta do sistema e a exatidão de algoritmos de oximetria. **Não inferir essa causa a partir do único teste de aquecimento.** Investigar em estudo separado, com mais participantes e controle dos fatores de confusão.
- **H4 — Limiares provisórios:** critérios fixos de contato e SQI herdados da bancada podem classificar como ausência de contato um dedo fisicamente presente, ou como contato um sinal sem pulsatividade suficiente.

**Separar fenômenos:** (a) presença física/óptica, (b) nível DC captado, (c) componente AC pulsátil e sua periodicidade, (d) qualidade do sinal e (e) SpO₂ matemática não calibrada. Esses conceitos não são equivalentes.

## 2. Estado atual efetivamente identificado no repositório

| Elemento | Estado observado | Implicação |
| --- | --- | --- |
| Sensor | **MAX30105** (não MAX30102) | Referências e hipóteses precisam identificar o componente correto. |
| Firmware | `MAX30105.h`, instância `MAX30105 max30105` | A classe SparkFun se chama MAX30105; não constitui calibração de oximetria. |
| Óptica | RED + IR; LED verde desativado | Não atribuir resultados ao canal GREEN, que não está coletando. |
| Aquisição | 100 SPS configurados, média FIFO de 4, ~25 amostras efetivas/s | Preservar timestamp, sequência, perdas e taxa efetiva nos ensaios. |
| Contato | `PPG_CONTACT_MIN = 5000` para RED e IR; confirmação por 3 amostras | Limiar provisório de intensidade, não prova de pulso fisiológico. |
| Gate 01 | Janelas de 5 s; mínimos de média e de faixa, entre outras verificações | PASS indica critérios de integridade, não validade clínica. |
| Python experimental | BPM por periodicidade do IR; SpO₂ DEMO por razão AC/DC RED/IR | Candidatos numéricos podem surgir do ruído; valores exibidos precisam respeitar contato/qualidade. |

**Arquivos relevantes, apenas para futura análise:** `arduino-pitaco-mpx5010dp-unity.ino`, `pitaco_ppg_sensor.ino`, `pitaco_ppg_contact_sqi.ino`, `gate_01_integrity.ino`, `pitaco_bridge/experimental.py`, `pitaco_bridge/monitor.py`, `pitaco_bridge/gui/oxy_and_cardio_view.py`.

## 3. Fundamentação e limites de transposição

1. **Temperatura e PPG.** Khan et al. (2015) avaliaram 20 adultos em condições basal, fria e aquecida e encontraram diferença importante na amplitude/qualidade PPG entre condições; o trabalho apoia testar o efeito da temperatura, mas não prova que o mesmo efeito terá a mesma magnitude no nosso MAX30105.
2. **Perfusão periférica e local de medida.** Estudos de PPG sob estresse térmico relatam alterações relevantes no sinal do dedo, compatíveis com vasoconstrição. A direção e magnitude dependem do local e do modo de aquisição.
3. **Pigmentação e outros fatores.** A FDA destaca pigmentação, circulação, temperatura e espessura da pele entre os fatores que afetam o desempenho da oximetria. Esse ponto motiva estratificação posterior, **não autoriza concluir que a participante do ensaio teve falha por pigmentação**.
4. **Adequação do componente.** A ficha do **MAX30105** o apresenta como sensor óptico de alta sensibilidade voltado primariamente à detecção de partículas, embora permita aplicações de reflexão óptica. Nosso protótipo de PPG/BPM e principalmente a SpO₂ por curva DEMO **não são funções clinicamente calibradas**. O estudo de Khan empregou outra configuração de sensor; seus valores de melhoria não devem ser transferidos quantitativamente ao MAX30105 sem medição local.

## 4. Pergunta de pesquisa

> No PITACO com MAX30105, mantendo aquisição, posicionamento e configuração óptica tão constantes quanto possível, o aquecimento confortável do dedo aumenta a modulação pulsátil RED/IR e a proporção de janelas com estimativa BPM estável, em comparação com condição inicial de dedo frio/ambiente?

### Resultados de interesse

- **Primários:** `AC_RMS / DC` separado para RED e IR (aproximação de modulação relativa, **não índice de perfusão calibrado**), periodicidade do IR, percentual de janelas com BPM Python estimável e percentual de janelas G1 PASS.
- **Secundários:** médias DC RED/IR, dispersão RMS/AC, amplitude pico-a-pico, correlação RED/IR, proporção `contact=true`, perdas sequenciais, gaps, taxa efetiva de amostras, tempo até primeira estimativa e discrepância de BPM frente a medidor de referência quando disponível.
- **Apenas exploratórios:** índice R e candidato de SpO₂ DEMO; **não interpretar sua estabilidade ou proximidade a 95–100% como evidência de exatidão**.
- Registrar explicitamente episódios com sinal acima do limiar DC, mas sem periodicidade suficiente, assim como contato aparente sem dedo.

## 5. Protocolo preliminar de coleta

**Tipo:** estudo exploratório intraindivíduo, sem inferência clínica; um episódio individual é gerador de hipótese, não confirmação estatística.

| Etapa | Duração sugerida | Condição | Observações |
| --- | --- | --- | --- |
| Controle sem dedo | 30–60 s | MAX30105 exposto, sem contato físico | Estimar nível residual RED/IR, falsos candidatos e falsos contatos. |
| A — inicial | 60 s | Dedo em sua temperatura espontânea; documentar se frio | Evitar aquecimento ou resfriamento provocados para iniciar. |
| B — ambiente | 60 s | Após estabilização confortável em ambiente | Registrar temperatura do dedo se houver medidor; sem deslocar o encaixe, se possível. |
| C — aquecido | 60 s | Dedo aquecido **suavemente**, sem calor excessivo | Registrar meio de aquecimento e temperatura, quando possível. |
| Retorno | 60 s (opcional) | Retorno gradual à condição confortável habitual | Verificar reversibilidade e efeito temporal. |

**Controle mínimo do procedimento:** mesma pessoa, mesmo dedo, mesma mão, mesmo encaixe/pressão, mesma iluminação e orientação, mesma corrente LED/ADC, taxa de aquisição e firmware. Registrar qualquer reposicionamento, movimento, retirada do dedo e possível atraso para estabilizar. Se a ordem não puder ser controlada, documentar efeito da ordem como limitação.

**Segurança e ética:** participação voluntária e consentida; evitar testes com frio intenso, aquecimento com objetos quentes, desconforto, dor ou riscos de queimadura. Suspender se houver dor, alteração importante da cor, dormência ou mal-estar. Não usar leituras experimentais do PITACO para decisões clínicas. Não registrar nomes, imagens identificáveis ou condições de saúde nos arquivos públicos do repositório.

**Comparador:** se houver, capturar BPM simultaneamente por instrumento independente de referência; registrar sua marca/modelo e condições de uso. Um oxímetro comercial pode auxiliar comparação exploratória da SpO₂, mas **não substitui padrão de calibração clínica**.

## 6. Plano de análise offline (sem modificar os algoritmos no PR)

Para cada janela contínua (sugerir janelas de 5 ou 8 s, claramente identificadas):

```text
RED/IR RAW + timestamp + flags G1/contacto
                |
                +--> DC_RED, DC_IR
                +--> AC_RED, AC_IR após remoção da tendência
                +--> M_RED = RMS(AC_RED) / DC_RED
                +--> M_IR  = RMS(AC_IR) / DC_IR
                +--> periodicidade, coerência RED/IR e artefatos
                +--> taxa efetiva, perdas e gaps
                |
        comparar A vs. B vs. C
        SEM trocar os limiares durante o ensaio
```

- Usar exatamente o mesmo tratamento de sinal nos três cenários; documentar janela e método de remoção DC.
- Não calcular `M` quando `DC <= 0`, amostras forem inválidas ou não houver janela temporal suficiente.
- Reportar mediana e dispersão por condição, proporção de janelas com estimativa BPM, gráficos RED/IR e os critérios que reprovaram cada janela.
- Comparar também o **tempo até primeiro BPM**, pois o aquecimento pode aumentar a detectabilidade antes de modificar valores de frequência.
- Evitar inferência causal ou estatística conclusiva com uma participante; replicar com várias pessoas, alternar condições quando for ético/seguro e separar grupos por características ópticas de modo planejado.
- Não ajustar automaticamente limiares de 5.000 contagens em função da temperatura observada: primeiro identificar se a falha é de DC, de AC, de periodicidade, do contato físico ou de transporte.

## 7. Critérios de interpretação e decisões futuras

- Se `contact=false` em dedo comprovadamente posicionado e `DC` insuficiente: revisar separadamente limiar/encaixe/corrente LED, após repetição controlada.
- Se `contact=true` mas `AC_RMS/DC` e periodicidade são insuficientes: considerar status próprio **“contato óptico presente — pulso insuficiente”**, separado do G1.
- Se o aquecimento alterar apenas DC, mas não a periodicidade: não afirmar melhora da qualidade fisiológica.
- Se a posição/pressão do dedo explicar as diferenças: considerar padronização de encaixe anatômico e proteção contra luz ambiente antes de alterar o SQI.
- Se a pigmentação for investigada no futuro: planejar amostra e critérios antes da coleta; não estimar tom de pele a partir do sinal RED/IR nem confundi-lo com circulação.
- Qualquer alteração futura em limiares, firmware, BPM, SpO₂, driver ou interface exige proposta e aprovação separadas.

## 8. Escopo deste PR

- [x] Documentar a observação, hipóteses, fatores de confusão e protocolo experimental.
- [x] Identificar corretamente o **MAX30105** e a configuração RED + IR.
- [x] Definir métricas e forma de comparação sem prometer calibração clínica.
- [x] Apresentar referências e limites da literatura.
- [ ] **Não** modificar código, thresholds, firmware, aquisição, SQI, cálculos, BLE/USB, Unity ou arquivos de teste.
- [ ] **Não** executar coleta com participantes nem declarar resultados não obtidos.

## 9. Referências (fontes externas, não evidências de validação do PITACO)

1. Analog Devices. *MAX30105 — High-Sensitivity Optical Sensor for Smoke Detection Applications* (datasheet e página do produto). https://www.analog.com/en/products/max30105.html
2. Khan, M. et al. (2015). *Investigating the Effects of Temperature on Photoplethysmography*. IFAC-PapersOnLine 48(20), 360–365. https://doi.org/10.1016/j.ifacol.2015.10.166
3. Khan, M. et al. (2016). *Analysing the effects of cold, normal, and warm digits on transmittance pulse oximetry*. Biomedical Signal Processing and Control, 26, 34–41. https://doi.org/10.1016/j.bspc.2015.12.006
4. *Photoplethysmography upon cold stress—impact of measurement site and acquisition mode* (2023). https://pmc.ncbi.nlm.nih.gov/articles/PMC10267461/
5. FDA. *Pulse Oximeter Basics* (fatores de circulação, temperatura e pigmentação da pele). https://www.fda.gov/consumers/consumer-updates/pulse-oximeter-basics

**Nota:** fontes sobre oxímetros por transmissão, diferentes geometrias ópticas e diferentes modelos de sensor apoiam hipóteses, mas **não validam diretamente o módulo MAX30105 do PITACO**.
