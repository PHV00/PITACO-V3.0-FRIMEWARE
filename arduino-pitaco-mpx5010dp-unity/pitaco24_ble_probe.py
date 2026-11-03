#!/usr/bin/env python3
"""Ensaio BLE de bancada: PPG, G1 e pressao sem iniciar a GUI/Unity.

Exemplo: python pitaco24_ble_probe.py --seconds 60 --csv ppg_ble_60s.csv
Requer bleak; grava CSV somente quando --csv e informado.
"""
import argparse
import asyncio
import csv
import time

from pitaco24_protocol import (
    BLE_PPG_BINARY_UUID, BleJsonlBuffer, decode_ble_ppg_frame, parse_pitaco_line
)

DEVICE_NAME = "PITACO V2.0"
PRESSURE_UUID = "3bcdff27-47fc-4a87-9684-7672c49d9266"
PPG_JSON_UUID = "3bcdff2a-47fc-4a87-9684-7672c49d9266"


async def run(seconds, csv_path):
    from bleak import BleakClient, BleakScanner

    discovered = await BleakScanner.discover(timeout=8.0)
    device = next((x for x in discovered if x.name == DEVICE_NAME), None)
    if device is None:
        raise RuntimeError("PITACO V2.0 nao encontrado via Bluetooth")

    stats = {
        "seq": None, "samples": 0, "missing": 0, "duplicates": 0,
        "backwards": 0, "invalid": 0, "g1": 0,
        "bpm_valid": 0, "pressure": 0, "echop": 0
    }
    pressure_bytes = bytearray()
    json_decoder = BleJsonlBuffer()
    latest_pressure = None
    csv_file = open(csv_path, "w", newline="", encoding="utf-8") if csv_path else None
    writer = csv.writer(csv_file) if csv_file else None
    if writer:
        writer.writerow(("received_s", "seq", "t_ms", "red", "ir", "bpm",
                         "bpm_valid", "contact", "g1", "reason", "last_pressure_pa"))

    def on_message(message):
        if message["type"] == "g1":
            stats["g1"] += 1
            print("G1", message.get("window"), message["sqi"])
            return
        if message["type"] != "sample":
            return
        seq = message["seq"]
        if stats["seq"] is not None:
            jump = (seq - stats["seq"]) & 0xFFFF
            if jump == 0:
                stats["duplicates"] += 1
            elif jump <= 32768:
                stats["missing"] += jump - 1
            else:
                stats["backwards"] += 1
        stats["seq"] = seq
        stats["samples"] += 1
        if message["ppg"].get("bpm_valid") is True:
            stats["bpm_valid"] += 1
        if writer:
            ppg = message["ppg"]
            sqi = message["sqi"]
            writer.writerow((
                "%.6f" % time.monotonic(), seq, message.get("t_ms"),
                ppg["red"], ppg["ir"], ppg.get("bpm"), ppg.get("bpm_valid"),
                sqi.get("contact"), sqi.get("g1"), sqi.get("reason"), latest_pressure
            ))

    def on_pressure(_sender, data):
        nonlocal latest_pressure
        for value in bytes(data):
            if value == 10:
                line = pressure_bytes.decode("ascii", errors="replace").strip()
                pressure_bytes.clear()
                if line == "echop":
                    stats["echop"] += 1
                msg = parse_pitaco_line(line)
                if msg and msg["type"] == "pressure":
                    stats["pressure"] += 1
                    latest_pressure = msg["mpx5010dp"]["pressure_pa"]
            else:
                if len(pressure_bytes) < 300:
                    pressure_bytes.append(value)
                else:
                    pressure_bytes.clear()

    def on_binary(_sender, data):
        try:
            message = decode_ble_ppg_frame(data)
        except ValueError:
            stats["invalid"] += 1
            return
        on_message(message)

    def on_json(_sender, data):
        for line in json_decoder.feed(bytes(data)):
            msg = parse_pitaco_line(line)
            if msg is None:
                stats["invalid"] += 1
            else:
                on_message(msg)

    try:
        async with BleakClient(device) as client:
            await client.start_notify(PRESSURE_UUID, on_pressure)
            try:
                await client.start_notify(BLE_PPG_BINARY_UUID, on_binary)
                transport = BLE_PPG_BINARY_UUID
                print("PPG: BLE compacto v1 (20 bytes por notificacao)")
            except Exception as exc:
                print("PPG binario indisponivel; fallback JSON:", exc)
                await client.start_notify(PPG_JSON_UUID, on_json)
                transport = PPG_JSON_UUID
                print("PPG: BLE JSONL legado")
            await client.write_gatt_char(PRESSURE_UUID, b"e", response=True)
            await asyncio.sleep(0.25)
            await client.write_gatt_char(PRESSURE_UUID, b"r", response=True)
            start = time.monotonic()
            try:
                while time.monotonic() - start < seconds:
                    await asyncio.sleep(min(5.0, max(0.05, seconds - (time.monotonic() - start))))
                    print("STATUS PPG", stats["samples"], "perdidas_seq", stats["missing"],
                          "invalidos", stats["invalid"], "pressao", stats["pressure"])
            finally:
                if client.is_connected:
                    await client.write_gatt_char(PRESSURE_UUID, b"f", response=True)
                    await client.stop_notify(transport)
                    await client.stop_notify(PRESSURE_UUID)
    finally:
        if csv_file:
            csv_file.close()

    print("RESULTADO: PPG", stats["samples"], "taxa=%.2f/s" % (stats["samples"] / seconds),
          "faltantes_seq", stats["missing"], "duplicadas", stats["duplicates"],
          "retrocedeu", stats["backwards"], "invalidas", stats["invalid"],
          "janelas G1", stats["g1"], "BPM validos", stats["bpm_valid"],
          "pressao", stats["pressure"], "echop", stats["echop"])
    if csv_path:
        print("CSV:", csv_path)
    print("A contagem de seq mede perdas observadas no destino, nao garante "
          "ausencia de perda na fonte nem na pilha BLE.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--csv", default=None, help="Caminho opcional para capturar RAW PPG")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds deve ser positivo")
    asyncio.run(run(args.seconds, args.csv))
