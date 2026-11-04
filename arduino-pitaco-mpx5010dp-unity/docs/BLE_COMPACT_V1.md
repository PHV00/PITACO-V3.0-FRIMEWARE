# Transporte PPG BLE compacto v1 — branch experimental

## Compatibilidade
O MPX5010DP, a pressão numérica BLE/USB, a OTA, os comandos e/r/f/c/z, a ponte Unity e o firmware original permanecem. O JSONL USB não muda. O canal BLE JSON anterior (UUID terminado em 2a) permanece como fallback.

Novo UUID (READ/NOTIFY): **3bcdff2b-47fc-4a87-9684-7672c49d9266**.
O cliente primeiro assina este UUID e envia o comando BLE **b** na characteristic antiga de comandos (3bcdff27-47fc-4a87-9684-7672c49d9266). O modo inicial por conexão é JSON; comando **j** retorna ao JSON antigo. O estado de modo é global à conexão ativa: uso com múltiplos clientes simultâneos exigiria remodelagem.

## Pacote binário fixo de 20 bytes

Todos os inteiros são little-endian; não requer MTU acima do mínimo ATT 23. O CRC16/CCITT-FALSE cobre bytes 0–17, polinômio 0x1021, valor inicial 0xFFFF, sem reflexão ou XOR final; o checksum fica em 18–19 (little-endian).

| Bytes | Amostra (tipo=01) | G1 (tipo=02) |
| --- | --- | --- |
| 0 | magic A5 | magic A5 |
| 1 | 01 | 02 |
| 2–3 | seq uint16 | window uint16 |
| 4–7 | t_ms uint32 | t_ms uint32 |
| 8–10 | RED uint24, RAW 18 bits | samples uint16 em 8–9; reason em 10 |
| 11–13 | IR uint24, RAW 18 bits | passed em 11; 12–13 reservados zero |
| 14–15 | BPM vezes 10; 0xFFFF se inválido | reservados zero |
| 16 | bit0=bpm_valid, bit1=contact, bit2=g1_ready, bit3=g1_pass | reservado zero |
| 17 | reason, de 0 a 10 | reservado zero |
| 18–19 | CRC16 | CRC16 |

Uma amostra RED/IR utiliza **uma notificação**. O evento G1 também utiliza uma. A pressão continua na characteristic antiga (~20 Hz) e não é duplicada. Não há compressão com perdas do PPG; somente BPM é quantizado para 0,1 BPM no pacote BLE. Os resultados raw JSONL USB permanecem iguais.

## Responsabilidades adicionadas

**Arduino:** blePut16/24/32 codificam inteiros; bleCrc16 calcula checksum; blePpgNotify emite 20 bytes; blePpgSubscribed verifica conexão, inscrição e modo; sendBlePpgSample envia amostra óptica/contato/BPM; sendBlePpgG1 envia janela. MyCallbacks recebe b/j só por GATT, mantendo todos os comandos anteriores. SendPpgJson continua enviando JSON no USB e envia notificações BLE JSON apenas no modo antigo.

**Python:** decode_ble_ppg_frame valida CRC, magic, tipo, limites e flags e retorna o mesmo dicionário sample/G1 usado no JSON. A GUI prefere binário, tenta fallback JSON se necessário e registra recebidas, faltantes_seq, duplicadas, inválidas e janelas G1. O coletor headless pitaco24_ble_probe.py faz medição BLE separadamente da GUI/Unity.

## Verificação (ainda não executada no hardware)

1. Gravar esta branch no ESP32-C3. O Windows pode reter cache GATT antigo; atualizar o cache/reemparelhar caso a nova characteristic não apareça.
2. Encerrar GUI, Unity e outros clientes BLE; manter apenas o coletor.
3. Em PowerShell, na pasta do sketch:

    python .\pitaco24_ble_probe.py --seconds 60 --csv ppg_ble_60s.csv

4. Confirmar ~25 amostras PPG/s, ~20 leituras de pressão/s, echop, janelas G1 e ausência de faltantes, duplicadas e frames inválidos. Repetir com GUI, Unity e gravação longa de 2–5 minutos.
5. Comparar logs USB X,PPG_DIAG com os contadores BLE para separar falha de FIFO de perda de transporte; os dados atuais só comprovam continuidade **em USB**.

Uma notificação BLE é fire-and-forget em nível de aplicação; CRC não recupera mensagens, apenas detecta quadros inválidos. A contagem de sequência permite mensurar perdas percebidas pelo receptor. Não afirmar sucesso BLE antes de ensaio com ESP32-C3 e Windows.
