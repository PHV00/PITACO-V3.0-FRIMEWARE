# PITACO 2.4 — BLE, USB, OTA e ponte Unity

**Fontes:** `../firmware/pitaco_2_4/pitaco_2_4.ino`, `../ble_client_mpx5010dp.py`, `../pitaco_bridge/gui/main_window.py` e `../pitaco_bridge/protocol.py`.

## GATT: manter compatibilidade com o original

Um serviço, **quatro** characteristics, mantendo o nome BLE PITACO V2.0.

| Papel | UUID | Contrato |
| --- | --- | --- |
| Service PITACO | 0f128d4d-3cf9-46de-bb31-ed159450d6cf | Serviço anunciado |
| Pressão/comandos legado | 3bcdff27-47fc-4a87-9684-7672c49d9266 | READ/WRITE/NOTIFY, pressão Pa em linha, echop e e/r/f/c/z |
| OTA controle legado | 3bcdff28-47fc-4a87-9684-7672c49d9266 | WRITE/NOTIFY; START 0x01 e tamanho 4 bytes, END 0x02, ABORT 0x03 |
| OTA dados legado | 3bcdff29-47fc-4a87-9684-7672c49d9266 | WRITE/WRITE_NR; dados binários do firmware |
| PPG JSONL novo | 3bcdff2a-47fc-4a87-9684-7672c49d9266 | READ/NOTIFY; RED/IR, BPM e G1 |

A characteristic PPG **não** recebe comandos: e/r/f/c/z continuam na characteristic de pressão legada. Pressão ainda sai como linha numérica a ~20 Hz tanto em USB como na BLE legada.

## O que faz cada função BLE/USB embarcada

| Função / callback | Operação |
| --- | --- |
| MyServerCallbacks.onConnect() | Marca cliente conectado |
| MyServerCallbacks.onDisconnect() | Marca desconectado e reativa advertising |
| MyCallbacks.onWrite() | Lê primeiro caractere na characteristic de pressão e chama ListenCommand |
| ListenCommand() | e: handshake echop/parar; r: iniciar; f: parar; c: recalibração curta; z: zero de 10 segundos |
| SendStatus() | Responde em USB e, se conectado, envia notify de pressão/status |
| OtaControlCallbacks.onWrite() | START chama Update.begin e pausa sessão; END chama Update.end e reinicia; ABORT aborta |
| OtaDataCallbacks.onWrite() | Grava dados OTA recebidos com Update.write enquanto OTA está ativa |
| setup() | Cria servidor BLE, serviço e quatro characteristics, inicia advertising e MAX30105 |
| loop() | Escuta USB, acompanha PPG, calibra e publica pressão numérica no USB e GATT antigo |
| SendPpgJson() | Imprime linha JSONL completa na USB; divide notificações BLE em blocos de no máximo 20 bytes |
| SendG1Json() | Gera evento JSONL type=g1 a cada janela |
| PollMAX30105() | Lê FIFO RED/IR, avalia contato, BPM e G1 e constrói evento JSONL type=sample |

**Amostras JSONL:** type=sample contém seq uint16, t_ms, ppg.red, ppg.ir, ppg.bpm, ppg.bpm_valid, mpx5010dp.pressure_pa/valid e sqi.g1/reason/contact. O evento type=g1 contém window, g1, reason e samples. g1=null significa janela ainda não avaliada. bpm=null e bpm_valid=false significam BPM indisponível. reason=10 marca contato ausente. A pressão embutida é a última leitura válida do MPX, não uma leitura simultânea.

O RAW RED/IR é transmitido mesmo quando G1 reprova, contanto que seja adquirido e enviado. No Bluetooth, JSONL é repartido em **até 20 bytes por notify** para MTU mínimo 23; o cliente precisa concatenar até LF. Zero salto seq visto no USB **não demonstra** ausência de perdas pelo BLE. BLE precisa de teste de throughput junto à pressão, sob carga.

## Cada função da ponte relacionada a comunicação

| Função | Responsabilidade |
| --- | --- |
| pitaco24_protocol.parse_pitaco_line() | Entende pressão numérica legada ou JSON sample/g1 e valida RED/IR e seq |
| pitaco24_protocol.BleJsonlBuffer.feed() | Junta bytes BLE até LF; descarta linhas indecodificáveis/excessivas |
| update_pressure_from_device() | Atualiza valor e gráfico do caminho de pressão/fluxo legado |
| process_pitaco_line() | Interpreta frames, registra RED/IR, BPM e G1 no monitor e encaminha pressão quando permitido |
| notification_handler() | Processa notificações legadas de pressão, zero e echop |
| ppg_notification_handler() | Reconstrói JSON da characteristic PPG e evita duplicar pressão ao chamar allow_pressure=False |
| serial_read_loop() | Encaminha comandos da COM virtual do jogo ao ESP32 via BLE ou USB |
| usb_read_device_loop() | Lê a USB física e interpreta pressão, PPG e status |
| ble_bridge() | Descobre/conecta dispositivo, assina as duas characteristics e gerencia desconexão |
| start_bridge()/stop_bridge() | Abre/encerra portas, conexão e threads |
| interpolation_loop() | Mantém atualização do fluxo/pressão enviado ao Unity |
| PressureFilter.process() | Filtro do fluxo estimado na GUI; não altera RAW óptico |

**Portas:** a COM física do ESP32 (quando usado USB) e a COM virtual do jogo respiratório devem ser distintas. **Não existe COM virtual de oxímetro**: MAX30102, BPM e G1 são recebidos do ESP32 pelo mesmo JSON PPG em USB/BLE. A Unity continua recebendo pressão pela COM do jogo; BPM/SpO₂ não são enviados à Unity por esta versão da ponte.

## Diagnóstico e testes

- X,PPG_STATE: STOPPED/COLLECTING; os erros ópticos não devem parar MPX.
- X,PPG_CONTACT: detector óptico experimental PRESENT/ABSENT.
- X,PPG_FIFO_OVERFLOW / X,PPG_SW_RING_OVERRUN: perdas de aquisição detectadas e G1 invalidado.
- X,PPG_DIAG: telemetria USB a cada 2 s; pode ser desativada por parâmetro.
- **Não mudar** UUIDs nem forma das mensagens sem migrar a ponte e a Unity.

Ver também ../README_BLE_TESTE.md (histórico e roteiro BLE) e ../README_TESTE_FIFO_PPG.md (ensaios da FIFO). Verificação host: python -m unittest discover -s tests -p test_*.py. A exatidão de BPM, SpO2 e equivalência BLE/USB ainda requer validação física.

## Middleware gráfico PPG (branch experimental isolada)

O programa ble_client_mpx5010dp.py remonta PPG JSONL por BLE e USB e encaminha pressão para a Unity pela COM do jogo respiratório. O BPM fica disponível na GUI via JSON, sem porta COM de oxímetro. O monitor também mostra RED/IR RAW, contato, Gate 01, perdas de sequência e grava CSV opcional. **Não muda UUID, firmware ou transporte BLE**. Consultar [PPG_GUI_MONITOR.md](PPG_GUI_MONITOR.md) para arquitetura, funções e procedimento de comparação USB/BLE.
