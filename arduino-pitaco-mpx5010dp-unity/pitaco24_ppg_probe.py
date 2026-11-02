#!/usr/bin/env python3
"""Coleta USB do PITACO 2.4 com MAX30105; nao calcula FC/SpO2."""
import argparse
import csv
import time


def parse_usb_record(line):
    """Aceita RAW com RED/IR (6 campos) ou RED/IR/GREEN (7 campos)."""
    fields = line.strip().split(",")
    try:
        if len(fields) in (6, 7) and fields[0] == "R":
            seq, ts, window, red, ir = map(int, fields[1:6])
            green = int(fields[6]) if len(fields) == 7 else None
            channels = [red, ir] if green is None else [red, ir, green]
            if any(x < 0 or x > 262143 for x in channels):
                return None
            return ("R", seq, ts, window, red, ir, green)
        if len(fields) == 6 and fields[0] == "Q":
            window, ts, passed, reason, count = map(int, fields[1:])
            return ("Q", window, ts, passed, reason, count)
        if fields[0] == "X":
            return ("X", line.strip())
        if len(fields) == 1:
            return ("P", float(fields[0]))
    except (ValueError, IndexError):
        return None
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("port", help="COM3 ou /dev/ttyACM0")
    p.add_argument("--seconds", type=float, default=35.0)
    p.add_argument("--csv", default="pitaco24_max30105.csv")
    a = p.parse_args()
    import serial  # python3 -m pip install pyserial

    raw_count = quality_count = 0
    prevseq = None
    gaps = 0
    with serial.Serial(a.port, 115200, timeout=0.5) as dev, open(
        a.csv, "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(["type", "sequence", "timestamp_ms", "window",
                         "red", "ir", "green", "pass", "reason", "count", "pressure_pa"])
        time.sleep(1.5)
        dev.write(b"e")
        time.sleep(0.15)
        dev.write(b"r")
        until = time.monotonic() + a.seconds
        try:
            while time.monotonic() < until:
                line = dev.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                record = parse_usb_record(line)
                if record is None:
                    if line != "echop":
                        print("IGNORED", line)
                    continue
                if record[0] == "R":
                    _, seq, ts, window, red, ir, green = record
                    if prevseq is not None:
                        gaps += max(0, ((seq - prevseq) & 65535) - 1)
                    prevseq = seq
                    writer.writerow(["R", seq, ts, window, red, ir,
                                     green if green is not None else "",
                                     "", "", "", ""])
                    raw_count += 1
                elif record[0] == "Q":
                    _, window, ts, passed, reason, count = record
                    writer.writerow(["Q", "", ts, window, "", "", "",
                                     passed, reason, count, ""])
                    print("G1", window, "PASS" if passed else "FAIL",
                          "reason", reason, "samples", count)
                    quality_count += 1
                elif record[0] == "X":
                    print("STATUS", record[1])
                elif record[0] == "P":
                    writer.writerow(["P", "", "", "", "", "", "",
                                     "", "", "", record[1]])
        finally:
            dev.write(b"f")
    print("RAW", raw_count, "G1", quality_count,
          "sequence_gaps", gaps, "CSV", a.csv)


if __name__ == "__main__":
    main()
