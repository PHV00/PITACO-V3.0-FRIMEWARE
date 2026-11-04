"""Protocolo PITACO 2.4: JSON Lines via USB e notificacoes BLE fracionadas.

Este modulo nao depende de Windows, UI, bleak ou pyserial; pode ser testado
isoladamente no PC. O envio de dados raw para G2+ usara os mesmos frames.
"""
import json
import math


def parse_pitaco_line(text):
    """Interpreta pressao numerica antiga e JSON PITACO 2.4. Retorna dict/None."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            msg = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(msg, dict) or msg.get("type") not in ("sample", "g1"):
            return None
        if msg["type"] == "sample":
            ppg = msg.get("ppg")
            if not isinstance(ppg, dict):
                return None
            for name in ("red", "ir"):
                val = ppg.get(name)
                if type(val) is not int or not 0 <= val <= 262143:
                    return None
            seq = msg.get("seq")
            if type(seq) is not int or not 0 <= seq <= 65535:
                return None
        return msg
    try:
        val = float(text)
        if math.isfinite(val):
            return {"type": "pressure", "mpx5010dp": {"pressure_pa": val, "valid": True}}
    except ValueError:
        pass
    return None


class BleJsonlBuffer:
    """Junta bytes de notificacoes da mesma characteristic ate LF.

    Quadros que ultrapassam max_line_bytes sao descartados. Dados perdidos
    no meio de linha ainda podem corromper JSON: o parser descarta quadros
    invalidos. O campo seq permite contagem de perdas posteriores.
    """
    def __init__(self, max_line_bytes=512):
        self.buf = bytearray()
        self.max_line_bytes = max_line_bytes

    def reset(self):
        self.buf.clear()

    def feed(self, data):
        completed = []
        for byte in data:
            if byte == 10:
                try:
                    completed.append(self.buf.decode("ascii"))
                except UnicodeDecodeError:
                    pass
                self.buf.clear()
            else:
                self.buf.append(byte)
                if len(self.buf) > self.max_line_bytes:
                    self.buf.clear()
        return completed
