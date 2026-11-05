#!/usr/bin/env python3
"""Coletor leve de dados JSONL e pressao legado do PITACO 2.4 via USB."""
import argparse
import csv
import time
import sys
from pathlib import Path

# Executado como script direto: raiz do projeto precisa estar em sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pitaco_bridge.protocol import parse_pitaco_line


def main():
    p = argparse.ArgumentParser()
    p.add_argument("port", help="COM3 ou /dev/ttyACM0")
    p.add_argument("--seconds", type=float, default=35.0)
    p.add_argument("--csv", default="pitaco24_capture.csv")
    a = p.parse_args()
    import serial

    raw_count = 0
    quality_count = 0
    prevseq = None
    gaps = 0
    with serial.Serial(a.port, 115200, timeout=0.5) as dev, open(
            a.csv, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["type", "seq", "t_ms", "red", "ir", "bpm",
                         "bpm_valid", "pressure_pa", "g1", "reason", "samples", "contact"])
        time.sleep(1.5)
        dev.write(b"e")
        time.sleep(0.15)
        dev.write(b"r")
        until = time.monotonic() + a.seconds
        try:
            while time.monotonic() < until:
                line = dev.readline().decode("ascii", errors="replace").strip()
                if line.startswith("X,"):
                    print("STATUS", line)
                    continue
                msg = parse_pitaco_line(line)
                if msg is None:
                    continue
                kind = msg["type"]
                if kind == "sample":
                    seq = msg["seq"]
                    ppg = msg["ppg"]
                    mpx = msg.get("mpx5010dp", {})
                    g1 = msg.get("sqi", {})
                    if prevseq is not None:
                        gaps += max(0, ((seq - prevseq) & 65535) - 1)
                    prevseq = seq
                    writer.writerow([kind, seq, msg.get("t_ms"),
                                     ppg["red"], ppg["ir"], ppg.get("bpm"),
                                     ppg.get("bpm_valid"), mpx.get("pressure_pa"),
                                     g1.get("g1"), g1.get("reason"), "",
                                     g1.get("contact")])
                    raw_count += 1
                elif kind == "g1":
                    quality_count += 1
                    g1 = msg.get("sqi", {})
                    print("G1", msg.get("window"), g1)
                    writer.writerow([kind, "", msg.get("t_ms"), "", "", "", "",
                                     "", g1.get("g1"), g1.get("reason"),
                                     g1.get("samples"), ""])
                elif kind == "pressure":
                    writer.writerow([kind, "", "", "", "", "", "",
                                     msg["mpx5010dp"]["pressure_pa"], "", "", "", ""])
        finally:
            dev.write(b"f")
    print("Amostras PPG", raw_count, "janelas G1", quality_count,
          "saltos de sequencia", gaps, "CSV", a.csv)


if __name__ == "__main__":
    main()
