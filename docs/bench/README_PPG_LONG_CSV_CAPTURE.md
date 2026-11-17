# Ensaio PPG: log completo de 2 minutos (USB/BLE)

## Objetivo

Registrar **todas** as amostras recebidas do PITACO 2.4 em uma sessao longa, inclusive quando contato e G1 sao reprovados. O teste investiga intermitencias da HUD da Unity sem alterar firmware, G1/SQI, calibração, filtros ou o algoritmo de BPM/SpO2.

## Passo a passo

1. Execute a aplicacao Python (arduino-pitaco-mpx5010dp-ble/ble_client_mpx5010dp.py).
2. Conecte ao PITACO por Cabo USB ou Bluetooth; aguarde amostras PPG recentes.
3. Abra o grafico de oximetria/cardio. Posicione o dedo e deixe-o parado.
4. Selecione **2 min** e clique em **Gerar log completo**.
5. Escolha o caminho e nome do arquivo pitaco24_ppg_full_YYYYMMDD_HHMMSS.csv.
6. Mantenha o dedo parado. O contador de segundos e linhas aparece na interface; a captura **termina automaticamente**.
7. Para abortar, clique em **Encerrar log completo**; se houver desconexao, a gravacao e encerrada e o arquivo parcial e preservado.

O botao **Gravar CSV PPG** continua manual: um clique inicia, outro encerra. Os dois modos compartilham o mesmo gravador, sem gravacoes simultaneas.

## Dados preservados

- type: sample, g1 e pressure (quando recebidos)
- transport: USB ou BLE
- rx_s: segundos decorridos desde o inicio da gravacao
- seq, t_ms, red, ir: sequencia, relogio do dispositivo e sinal bruto
- bpm, bpm_valid: BPM calculado pelo firmware e validade
- g1, reason, samples, window, contact: qualidade e contato
- pressure_pa: pressao, quando recebida

O gravador salva em disco em thread separada, sem o limite do buffer do grafico. Nao recupera amostras anteriores ao clique, nem inventa mensagens perdidas na transmissao. Verifique **descartadas: 0** ao finalizar.

## Criterios para analisar a captura

A 25 Hz, um ensaio de 120 s deve ter aproximadamente 3000 linhas sample e 24 eventos G1 de cinco segundos, alem de pressao quando presente. Pequenas diferencas podem decorrer da temporizacao. Cheque a duracao em rx_s, t_ms e os saltos da sequencia seq.

Para investigar G1 reason=4, agrupe as amostras por janelas do firmware e calcule amplitude max(red)-min(red), media RED/IR, contato e descontinuidades de sequencia. Compare com janelas aprovadas (reason=0) e com o horario de aparecimento de -- na HUD da Unity.

SpO2 segue experimental e nao calibrada. Este ensaio nao constitui validacao clinica.

## Testes automatizados

Execute na raiz do repositorio:

    python -m unittest discover -s test -p "test_ppg_long_csv_capture.py" -v

O teste simula 120 s a 25 Hz e verifica 3000 amostras + 24 janelas G1, preservacao das falhas e zero descartes. Nao substitui o teste fisico no ESP32.
