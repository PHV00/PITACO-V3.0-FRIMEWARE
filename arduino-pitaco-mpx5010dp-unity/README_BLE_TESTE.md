# PITACO 2.0 — teste BLE com MPX5010DP (experimental)

Este teste usa o mesmo firmware da pasta, preservando firmware e cliente GUI legados.
A leitura enviada pelo ESP32 ja e **pressao relativa em Pa**, assinada e com zona morta.
**Nao e fluxo calibrado (L/min)**. Valores negativos relativos ao offset nao
comprovam medicao fisica inspiratoria negativa pelo MPX5010DP.

## Arquivos

- arduino-pitaco-mpx5010dp-unity.ino: firmware de teste ESP32-C3 com USB e BLE.
- ble_client_mpx5010dp.py: novo cliente Python para validar BLE e fazer ponte para Unity.
- O cliente GUI antigo, na pasta arduino-pitaco-ble, permanece **inalterado**.
  Ele usa uma estimativa de fluxo baseada em orificio; nao confundir com Pa.

## Preparacao

No Windows, habilitar Bluetooth. Energizar ESP32-C3 com firmware de teste.
USB pode continuar conectada para alimentacao, mas feche Monitor Serial,
Unity e outros aplicativos ja conectados ao BLE.

Instalar Python 3.10+ e dependencias:

    python -m pip install bleak pyserial

## Teste 1: BLE independente (sem Unity ou COM virtual)

No terminal, dentro desta pasta:

    python ble_client_mpx5010dp.py --seconds 30

O cliente busca PITACO V2.0, conecta, ativa NOTIFY, envia e, exige echop,
envia r, mostra pressao relativa assinada por ~30s e encerra enviando f.

Saida ilustrativa:

    [BLE] Conectado a PITACO V2.0.
    [BLE] Identificacao: echop
    [PRESSAO RELATIVA Pa] 0.00
    [PRESSAO RELATIVA Pa] 35.21
    [PRESSAO RELATIVA Pa] -42.18
    [TESTE] ... leituras recebidas.

Para recalibrar o repouso, sem tocar no bocal na calibracao:

    python ble_client_mpx5010dp.py --seconds 30 --calibrate

O comando c calcula uma nova referencia por cerca de 1,2s.
ATENCAO: o firmware volta a usar referencia fixa de 100 Pa na proxima
sessao, se nao for enviado c novamente.

## Teste 2: BLE -> porta COM virtual -> Unity (depois do Teste 1)

Configurar par com0com funcional, por exemplo CNCA0 <-> CNCB0.
Executar primeiro a ponte, usando uma extremidade:

    python ble_client_mpx5010dp.py --bridge-port CNCA0

Iniciar I Blue It depois. O jogo deve identificar o PITACO na OUTRA
extremidade (CNCB0), enviando e e recebendo echop. Comandos e/r/f/c
sao encaminhados por BLE; o cliente entrega linhas de pressao relativa
a 115200 baud via COM virtual. Nao abre COM3 (USB fisico).

Nao abrir CNCA0 simultaneamente em Unity e no cliente.
O jogo pode registrar 'acesso negado' em CNCA0 durante varredura,
mas deve conseguir conectar a CNCB0.

O jogo pode precisar de calibracao/sensibilidade, pois recebe Pa relativos,
NAO fluxo metrologicamente calibrado.

## Interpretacao

- Nao encontra dispositivo: conferir radio do PC, anuncio, firmware e outro cliente.
- Conecta sem echop: verificar NOTIFY/WRITE e callbacks do firmware.
- Echop sem numeros: verificar comando r e estado de amostragem.
- BLE funciona mas Unity nao: investigar par com0com e handshake da Unity.

Apenas sintaxe Python e decodificador foram testados sem hardware.
O teste efetivo com ESP32-C3 e Windows ainda precisa ser realizado.
