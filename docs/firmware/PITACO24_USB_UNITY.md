# PITACO 2.4 — identidade USB direta no I Blue It

## Escopo desta etapa
Esta mudanca altera **somente o orquestrador do firmware** e adiciona
um teste de contrato. Nao altera os arquivos do BLE, as caracteristicas
GATT, a Bridge Python, os sensores, as taxas nem os modulos SQI.

| Canal | Envio | Resposta |
| --- | --- | --- |
| USB legado | `e` ou `E` | `echop\n` |
| USB PITACO 2.4 | `i` | `echo2.4p\n` |
| BLE legado | `e` | `echop\n` na characteristic original |
| Sessao | `r`, `f`, `c`, `z` | Rotinas originais |

**Por que usar `i`?** O firmware e a Bridge Python antigos ja usam `e`
para `echop`. Substituir essa resposta quebraria o handshake existente.
O comando novo `i` e independente, nao inicia ou para amostragem e nao
executa `ListenCommand`; seu uso nao interfere com uma sessao ativa.

## Fluxo alvo

```
PITACO 2.4 (ESP32-C3) -- USB Serial 115200 --> Unity (receptor C)
     |                                       |
     +-- JSONL sample: pressure, RED, IR --> +-- OnJsonReceived(raw JSON)
     +-- JSONL g1 ------------------------>  +-- futuro integrador
     +-- pressao numerica (legado) ------>  (C ignora linhas nao JSON)
```

O firmware **continua** enviando RAW RED/IR e os eventos G1. BPM e
SpO2 no Unity ainda nao fazem parte desta etapa.

## Requisitos de teste

1. Compilar `frimeware2.4/frimeware2.4.ino` para ESP32-C3.
2. Gravar o firmware atualizado apenas no ESP32 utilizado para o teste.
3. Com o Unity fechado e a Bridge fechada, abrir a porta fisica com
   monitor serial em 115200 baud:
   - enviar `i`: deve responder `echo2.4p`;
   - enviar `e`: deve responder `echop`;
   - enviar `r`: deve produzir pressao numerica, JSON `sample`,
     e eventos `g1` (com sensor inicializado).
4. **Fechar o monitor serial antes de abrir a Unity.** Nao e possivel
   manter a mesma porta aberta simultaneamente por dois programas.
5. No Unity, o receptor C deve identificar `echo2.4p` e registrar
   contagens de quadros JSON a cada 250 amostras.
6. Com a Unity fechada, testar a Bridge Python antiga por BLE e os
   graficos Pneumo e Cardio, preferencialmente em `Somente monitor`.
   A interface Python foi deixada **inalterada** neste PR.

## CI
- `python -m unittest discover -s test -p test_*.py`
- `arduino-cli compile --fqbn esp32:esp32:esp32c3 frimeware2.4`

**Limites:** o reconhecimento C usa USB direto, nao BLE; a identidade
fisica `PITACO V2.0` de advertising BLE nao foi alterada. O receptor
legado A continua reconhecendo `e/echop`; o C deve adquirir sua COM
antes da inicializacao das cenas. Concorrencia e reconexao precisam
ser verificadas em hardware.
