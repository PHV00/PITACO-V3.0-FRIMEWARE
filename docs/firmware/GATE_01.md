# SQI Gate 01 — contrato, parâmetros e funções

**Implementação efetiva:** ../sqi/gate_01_integrity.ino. É um verificador de integridade básica de RED/IR (18 bits), não um filtro, reconstrutor de sinal ou estimador fisiológico. Ele não modifica nem descarta amostras; a aquisição e o envio JSONL são responsabilidade do orquestrador.

## Constantes atuais (provisórias)

| Nome | Valor | Interpretação |
| --- | ---: | --- |
| G1_ADC_MAX | 262143 | Máximo esperado do ADC 18 bits |
| G1_MIN_MEAN | 5000 | Média mínima exigida em RED e IR |
| G1_MIN_RANGE | 500 | Máximo menos mínimo exigido em RED e IR |
| G1_CLIP_START | 260095 | Limiar de quase saturação: ADC_MAX - 2048 |
| G1_MIN_SAMPLES | 50 | Quantidade mínima de pares na janela |

Os limites vieram de bancada e precisam de calibração. Um período com sinal elevado e transição grande pode passar mesmo sem onda pulsátil útil.

## Cada variável e função

| Nome | Tipo / função | Detalhe |
| --- | --- | --- |
| g1RedMin/Max; g1IrMin/Max | Extremos | Mínimo/máximo de cada canal na janela |
| g1RedSum, g1IrSum | Acumulador uint64_t | Soma para médias por canal |
| g1Samples | Contador uint16_t | Total de pares consumidos |
| g1RedClips, g1IrClips | Contadores | Valores maiores ou iguais a G1_CLIP_START |
| g1Gap | Booleano | Marca integridade da aquisição comprometida |
| g1Reset() | void | Reinicia estatísticas, contadores e gap |
| g1Add(red, ir) | void | Acumula RED/IR bruto, mínimos, máximos, somas, clips e contador; se chegar a UINT16_MAX marca gap |
| g1MarkAcquisitionGap() | void | Sinaliza perda/atraso de leitura da FIFO ou ring de software |
| g1Evaluate(&reason,&samples) | bool | Retorna PASS somente se nenhuma condição abaixo reprovar; preenche motivo e contagem; ponteiros nulos retornam false |

## Ordem exata da decisão (primeiro motivo vence)

| Ordem | Condição | Reason |
| ---: | --- | --- |
| 1 | Nenhuma amostra | 1 = NO_SAMPLES |
| 2 | g1Gap sinalizado | 9 = GAP |
| 3 | Menos de 50 pares | 8 = TOO_FEW |
| 4 | Média RED abaixo de 5000 | 2 = RED_LOW |
| 5 | Média IR abaixo de 5000 | 3 = IR_LOW |
| 6 | Amplitude RED abaixo de 500 | 4 = RED_FLAT |
| 7 | Amplitude IR abaixo de 500 | 5 = IR_FLAT |
| 8 | Algum RED quase saturado | 6 = RED_CLIP |
| 9 | Algum IR quase saturado | 7 = IR_CLIP |
| 10 | Nada disso | 0 = PASS |

**Reason 10 = CONTACT_ABSENT não pertence ao algoritmo g1Evaluate.** Ele é gerado pelo detector de contato do orquestrador PollMAX30105 e pode invalidar o resultado efetivo de uma amostra ou janela.

## Integração temporal

PollMAX30105 chama g1Add para cada par. Aproximadamente a cada PPG_WINDOW_MS=5000 ms, chama g1Evaluate, envia type=g1 e reinicia a janela. A troca de estado óptico também reinicia janela e estado de validade; antes da primeira avaliação, g1=null significa **não avaliado**. A última decisão pode acompanhar as amostras posteriores.

Mesmo com G1 false, os pares RED/IR brutos continuam sendo emitidos em type=sample, desde que adquiridos e transmitidos com sucesso. O detector de contato usa PPG_CONTACT_MIN=5000 e três amostras consecutivas; é pré-condição independente do G1.

**Testes:** test/test_sqi_gate1.cpp exercita o mesmo arquivo .ino sem duplicar sua lógica. O histórico de falhas e ensaios fica em ../bench/README_TESTE_FIFO_PPG.md. Não relaxar thresholds com base apenas em percentuais PASS.
