"""PITACO 2.0 / MPX5010DP: monitor BLE e ponte BLE -> porta virtual Unity.

O sinal recebido ja e pressao relativa assinada (Pa), nunca fluxo validado (L/min).
O cliente nao altera a escala, a polaridade nem executa segunda calibracao.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
import time

DEVICE_NAME = "PITACO V2.0"
SERVICE_UUID = "0f128d4d-3cf9-46de-bb31-ed159450d6cf"
DATA_UUID = "3bcdff27-47fc-4a87-9684-7672c49d9266"
BAUDRATE = 115200


class LineDecoder:
    """Reconstrucao de linhas mesmo com fragmentacao/agregacao BLE."""

    def __init__(self, max_line_bytes=96):
        self._buffer = bytearray()
        self._discarding = False
        self.max_line_bytes = max_line_bytes

    def feed(self, chunk: bytes) -> list[str]:
        output = []
        for byte in chunk:
            if byte == 10:  # newline
                if not self._discarding and self._buffer:
                    try:
                        output.append(self._buffer.decode("ascii").strip())
                    except UnicodeDecodeError:
                        pass
                self._buffer.clear()
                self._discarding = False
            elif not self._discarding:
                if len(self._buffer) < self.max_line_bytes:
                    self._buffer.append(byte)
                else:
                    self._buffer.clear()
                    self._discarding = True
        return [line for line in output if line]


def valid_pressure(line: str) -> bool:
    """Aceita somente numeros finitos; mantem a representacao textual original."""
    try:
        return math.isfinite(float(line))
    except ValueError:
        return False


async def run(args: argparse.Namespace) -> None:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise RuntimeError("Instale bleak: python -m pip install bleak") from exc

    port = None
    decoder = LineDecoder()
    identified = asyncio.Event()
    forward_to_game = False
    sample_count = 0
    print(f"[BLE] Procurando '{args.device}'...", flush=True)

    device = await BleakScanner.find_device_by_name(args.device, timeout=args.scan_timeout)
    if device is None:
        raise RuntimeError("Dispositivo nao encontrado. Confira energia, anuncio BLE e outros clientes.")

    def notification_handler(_sender, data):
        nonlocal sample_count
        for line in decoder.feed(bytes(data)):
            if line == "echop":
                identified.set()
                print("[BLE] Identificacao: echop", flush=True)
                if port is not None and forward_to_game:
                    port.write(b"echop\r\n")
            elif valid_pressure(line):
                sample_count += 1
                if port is not None and forward_to_game:
                    # Mantem valor assinado em Pa; SEM converter por Bernoulli.
                    port.write((line + "\r\n").encode("ascii"))
                elif port is None:
                    print(f"[PRESSAO RELATIVA Pa] {line}", flush=True)
            else:
                print(f"[BLE] Mensagem ignorada: {line!r}", flush=True)

    async with BleakClient(device, timeout=15.0) as client:
        print(f"[BLE] Conectado a {device.name}.", flush=True)
        if not any(str(svc.uuid).lower() == SERVICE_UUID for svc in client.services):
            raise RuntimeError("Servico BLE PITACO ausente: firmware incorreto?")
        if not any(str(ch.uuid).lower() == DATA_UUID
                   for svc in client.services for ch in svc.characteristics):
            raise RuntimeError("Caracteristica de pressao do PITACO ausente.")

        await client.start_notify(DATA_UUID, notification_handler)
        await client.write_gatt_char(DATA_UUID, b"e", response=True)
        try:
            await asyncio.wait_for(identified.wait(), timeout=5.0)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Conectou ao BLE, mas nao recebeu echop.") from exc

        try:
            if args.bridge_port:
                try:
                    import serial
                except ImportError as exc:
                    raise RuntimeError("Instale pyserial: python -m pip install pyserial") from exc
                port = serial.Serial(args.bridge_port, BAUDRATE, timeout=0,
                                     write_timeout=0.5)
                forward_to_game = True
                print(f"[PONTE] Aberta {args.bridge_port} a 115200. "
                      "Unity deve abrir a OUTRA ponta do par com0com.", flush=True)
                print("[PONTE] Aguardando comandos e/r/f/c da Unity. Ctrl+C encerra.",
                      flush=True)
                while client.is_connected:
                    received = port.read(port.in_waiting or 1)
                    for byte in received:
                        if byte in b"eErRfFcC":
                            cmd = bytes([byte]).lower()
                            await client.write_gatt_char(DATA_UUID, cmd, response=True)
                            print(f"[JOGO -> BLE] {cmd.decode('ascii')}", flush=True)
                    await asyncio.sleep(0.01)
            else:
                print("[TESTE] Enviando r. As leituras sao relativas, em Pa.", flush=True)
                await client.write_gatt_char(DATA_UUID, b"r", response=True)
                if args.calibrate:
                    print("[TESTE] Enviando c. Deixe o bocal parado ~1,5 s.", flush=True)
                    await client.write_gatt_char(DATA_UUID, b"c", response=True)
                    await asyncio.sleep(1.5)
                end = time.monotonic() + args.seconds
                while time.monotonic() < end and client.is_connected:
                    await asyncio.sleep(0.1)
        finally:
            forward_to_game = False
            if port is not None:
                port.close()
                port = None
            if client.is_connected:
                try:
                    await client.write_gatt_char(DATA_UUID, b"f", response=True)
                except Exception as exc:
                    print(f"[BLE] Nao foi possivel enviar f: {exc}", flush=True)
            print(f"[TESTE] {sample_count} leituras recebidas.", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Teste BLE independente ou ponte BLE->COM para I Blue It."
    )
    parser.add_argument("--device", default=DEVICE_NAME)
    parser.add_argument("--scan-timeout", type=float, default=12.0)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--calibrate", action="store_true",
                        help="Envia c depois de r (calibre em repouso)")
    parser.add_argument("--bridge-port", metavar="CNCA0",
                        help="COM virtual aberta pelo cliente, oposta a COM da Unity")
    args = parser.parse_args()
    if args.seconds <= 0 or args.scan_timeout <= 0:
        parser.error("--seconds e --scan-timeout devem ser positivos")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[BLE] Encerrado.")
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)
