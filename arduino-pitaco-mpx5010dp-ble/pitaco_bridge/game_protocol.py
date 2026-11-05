"""Contrato de transporte do PITACO 2.4 para uma COM virtual do Unity.

A identificacao C nao pode conter "echop" nem "echox", pois os receptores
legados usam comparacao por substring. O JSON de amostras nao e reduzido
a valores de BPM: RED/IR seguem integrais para processamento no Unity.
"""
from .protocol import parse_pitaco_line

GAME_OUTPUT_PITACO24_JSON = "PITACO 2.4 (JSON)"
PITACO24_ECHO = b"echo2.4p\r\n"
MAX_UNITY_JSON_BYTES = 512


def encode_pitaco24_json(line):
    """Retorna uma linha JSON ASCII valida do firmware, ou None.

    Preserva o texto original (sem alterar seq, timestamps ou canais PPG).
    Quadros numericos legados e linhas de diagnostico nao pertencem ao canal C.
    """
    if not isinstance(line, str):
        return None
    raw = line.strip()
    if not raw or "\n" in raw or "\r" in raw:
        return None
    message = parse_pitaco_line(raw)
    if message is None or message.get("type") not in ("sample", "g1"):
        return None
    try:
        payload = raw.encode("ascii")
    except UnicodeEncodeError:
        return None
    if len(payload) > MAX_UNITY_JSON_BYTES:
        return None
    return payload + b"\r\n"


def route_combo_unity_command(data):
    """Separa a sondagem 'e' dos comandos reais ao ESP32.

    A identificacao C ocorre exclusivamente na Bridge; um 'e' fisico
    dispararia 'echop' do firmware, ambiguo para o receptor legado A.
    """
    if not isinstance(data, bytes):
        raise TypeError("expected bytes")
    response = PITACO24_ECHO if b"e" in data.lower() else None
    forward = bytes(b for b in data if b not in (ord("e"), ord("E")))
    return response, forward
