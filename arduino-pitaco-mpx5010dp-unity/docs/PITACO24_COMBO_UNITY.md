# PITACO 2.4 Combo — contrato de uma COM para Unity

Esta branch adiciona uma **terceira opção de Saída ao jogo** no middleware,
sem afetar os dois modos anteriores (pressão Pa e fluxo estimado L/min).
Não altera USB/BLE, firmware, MAX30102, MPX5010DP ou cálculo experimental.

| Entrada ESP32 → Python | Saída Python → Unity |
|---|---|
| USB ou BLE com JSON PPG e canal legado de pressão | A **mesma COM virtual do PITACO** para todos os modos |
| Pressão e MAX30102 integrados | `echop` e comandos `e/r/f/c/z` permanecem |
| BPM de firmware validado por G1/contato | Campo BPM opcional no modo combinado |
| SpO₂ Python experimental | **Nunca transmitida**; campo reservado sempre vazio |

## Formato e opções

- `Pressão relativa (Pa)`: legado, uma linha numérica: `-23.15\r\n`.
- `Fluxo estimado (L/min)`: legado, uma linha numérica: `18.24\r\n`.
- `PITACO 2.4 Combo`: `P24,-23.15,72.5,,1,1\r\n`.

A terceira opção é um *envelope* etiquetado para o mesmo receptor COM:

```text
P24,<respiracao_em_Pa>,<bpm_firmware_ou_vazio>,<spo2_vazio>,<g1_0_ou_1>,<contato_0_ou_1>
```

**Exemplos:**

```text
P24,-23.15,72.5,,1,1     # pressão e BPM FW qualificado
P24,10.25,,,1,1         # pressão, sem BPM estimável
P24,10.25,,,0,0         # pressão, sem janela/contato recente
```

O BPM é omitido quando o G1 ou contato falha, não há estimativa válida
ou as últimas amostras possuem 2 segundos ou mais. O campo SpO₂
é *sempre vazio* porque a fórmula experimental não é calibrada.

No Unity, `SerialControllerPitaco` identifica `P24,`, extrai o primeiro
valor numérico e o encaminha ao evento respiratório
`OnSerialMessageReceived`, preservando jogos existentes. Separadamente
um evento tipado entrega BPM e flags para UI/ML-Agents. Não há duas
conexões seriais, nem dependência de BLE dentro do Unity.

O modo legado de oxímetro separado (`SerialControllerOximetro`) permanece
nos arquivos Unity e não é alterado/mesclado fisicamente. É uma opção
anterior preservada, não um requisito para o novo modo P24.

### Limite da integração com ML-Agents

- O novo frame pode adicionar uma observação opcional de BPM e um indicador
  de validade ao DeepDDA, **somente com opt-in**.
- Ativar novas observações exige ajustar `BehaviorParameters` e treinar
  novamente o modelo. Um modelo pré-treinado com outra dimensão **não
  deve ser executado com esta opção ligada**.
- SpO₂ experimental não alimenta observações, recompensas nem painéis de
  segurança; sua utilização demanda calibração e validação próprias.

### Validação pendente

Testes de enquadramento, validade e compatibilidade são executados em
Python pelo GitHub Actions. Falta abrir a versão Unity e executar os
dois modos (legado e combo) com COM virtual e ESP32 físico.
