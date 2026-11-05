# PITACO 2.4 — Bridge para receptor C do I Blue It

O PITACO 2.4 e um unico dispositivo fisico (MPX5010DP + MAX30102).
A escolha USB/BLE nao altera o protocolo do jogo.

## Modos de saida

- `Pressao relativa (Pa)`: modo legado A — continua linha numerica, handshake `e` -> `echop` encaminhado do ESP32.
- `Fluxo estimado (L/min)`: modo legado A — idem.
- `PITACO 2.4 (JSON)`: modo C — **uma** COM virtual, handshake `e` -> `echo2.4p`, JSON por linha (CRLF), com RED, IR, seq, timestamp, SQI, pressao e BPM experimental do firmware preservados.

O `e` e respondido diretamente na Bridge em modo C e nao vai ao firmware. Nos modos legados, comandos e echo seguem o caminho original.

## Alteracoes

- `pitaco_bridge/game_protocol.py`: contrato de identidade, separacao do comando `e` e encoder para JSON integral, com limite de linha.
- `pitaco_bridge/gui/main_window.py`: adiciona modo na GUI, encaminha `sample` e `g1` com lock de escrita, desabilita interpolacao numerica em modo C e mantem modo congelado durante conexao.
- `test/test_game_protocol.py`: teste de echo exclusivo, roteamento de `e/r/f`, preservacao de RED/IR e rejeicao de quadros invalidos.

A opcao C nao calcula SpO2. O Unity recebera os dados brutos para seu proprio modulo de oximetria na etapa seguinte.

## Validacao

```powershell
$env:PYTHONPATH = "arduino-pitaco-mpx5010dp-ble"
python -m unittest discover -s test -p "test_game_protocol.py" -v
```

Execute a partir da raiz do repositorio. Os demais testes da bridge continuam disponiveis com `python -m unittest discover -s test -p "test_*.py"`.

**Pendentes:** testes com COM virtual Windows e Unity 2022.3.4f1, USB/BLE, reconexao e contagem de perdas pelo `seq`. O antigo PR #6 fornece P24 reduzido; nao combinar ambos os formatos sem deliberar sobre compatibilidade.
