"""Protocolo PITACO 2.4: JSON Lines via USB e notificacoes BLE fracionadas.

Este modulo nao depende de Windows, UI, bleak ou pyserial; pode ser testado
isoladamente no PC. O envio de dados raw para G2+ usara os mesmos frames.
"""
import json
import math
import binascii
import struct


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


# BLE PPG compacto v1: USB e characteristic JSON anterior seguem JSONL.
BLE_PPG_BINARY_UUID = "3bcdff2b-47fc-4a87-9684-7672c49d9266"
BLE_PPG_BINARY_SIZE = 20


def decode_ble_ppg_frame(data):
    """Decodifica frame v1 para a mesma estrutura dict de JSONL.

    Layout: magic A5, tipo, seq/window u16 LE, t_ms u32 LE,
    payload nos bytes 8..17 e crc16/CCITT-FALSE LE nos bytes 18..19.
    Pressao chega na characteristic BLE legada, separadamente.
    """
    data = bytes(data)
    if len(data) != BLE_PPG_BINARY_SIZE or data[0] != 0xA5:
        raise ValueError("BLE PPG: comprimento ou magic incorreto")
    crc_received = struct.unpack_from("<H", data, 18)[0]
    if binascii.crc_hqx(data[:18], 0xFFFF) != crc_received:
        raise ValueError("BLE PPG: CRC16 invalido")
    kind = data[1]
    index, t_ms = struct.unpack_from("<HI", data, 2)
    if kind == 1:
        red = int.from_bytes(data[8:11], "little")
        ir = int.from_bytes(data[11:14], "little")
        bpm10 = struct.unpack_from("<H", data, 14)[0]
        flags, reason = data[16], data[17]
        if red > 262143 or ir > 262143 or flags & 0xF0 or reason > 10:
            raise ValueError("BLE PPG: campo fora da faixa")
        bpm_valid = bool(flags & 1)
        contact = bool(flags & 2)
        g1_ready = bool(flags & 4)
        g1_pass = bool(flags & 8)
        if g1_pass and not g1_ready:
            raise ValueError("BLE PPG: G1 PASS sem janela avaliada")
        if bpm_valid and (bpm10 == 0xFFFF or not contact or not g1_pass):
            raise ValueError("BLE PPG: BPM invalido/inconsistente")
        if not bpm_valid and bpm10 != 0xFFFF:
            raise ValueError("BLE PPG: sentinela BPM invalida")
        return {
            "type": "sample", "seq": index, "t_ms": t_ms,
            "ppg": {
                "red": red, "ir": ir,
                "bpm": (bpm10 / 10.0) if bpm_valid else None,
                "bpm_valid": bpm_valid
            },
            "sqi": {
                "g1": (g1_pass if g1_ready else None) if contact else False,
                "reason": reason, "contact": contact
            }
        }
    if kind == 2:
        samples = struct.unpack_from("<H", data, 8)[0]
        reason, passed = data[10], data[11]
        if (reason > 10 or passed not in (0, 1) or passed != (reason == 0)
                or any(data[12:18])):
            raise ValueError("BLE PPG: janela G1 inconsistente")
        return {
            "type": "g1", "window": index, "t_ms": t_ms,
            "sqi": {"g1": bool(passed), "reason": reason, "samples": samples}
        }
    raise ValueError("BLE PPG: tipo ou versao desconhecido")
