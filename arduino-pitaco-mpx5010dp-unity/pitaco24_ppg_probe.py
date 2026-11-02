#!/usr/bin/env python3
"""Captura USB de bancada para experimentos posteriores; nao calcula SpO2."""
import argparse
import csv
import time

def main():
    p = argparse.ArgumentParser()
    p.add_argument("port", help="COM3 ou /dev/ttyACM0")
    p.add_argument("--seconds", type=float, default=35.0)
    p.add_argument("--csv", default="pitaco24_capture.csv")
    a = p.parse_args()
    import serial
    raw_count = quality_count = 0
    prevseq = None
    gaps = 0
    with serial.Serial(a.port, 115200, timeout=0.5) as dev, open(
        a.csv, "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(["type","sequence","timestamp_ms","window",
                         "red","ir","pass","reason","count","pressure_pa"])
        time.sleep(1.5)
        dev.write(b"e")
        time.sleep(0.15)
        dev.write(b"r")
        end = time.monotonic() + a.seconds
        try:
            while time.monotonic() < end:
                line = dev.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                fields = line.split(",")
                try:
                    if len(fields) == 6 and fields[0] == "R":
                        seq, ts, wid, red, ir = map(int, fields[1:])
                        if prevseq is not None:
                            gaps += max(0, ((seq - prevseq) & 0xffff) - 1)
                        prevseq = seq
                        writer.writerow(["R",seq,ts,wid,red,ir,"","","",""])
                        raw_count += 1
                    elif len(fields) == 6 and fields[0] == "Q":
                        wid, ts, passed, reason, count = map(int,fields[1:])
                        writer.writerow(["Q","",ts,wid,"","",passed,reason,count,""])
                        print("G1", wid, "PASS" if passed else "FAIL",
                              "reason",reason,"samples",count)
                        quality_count += 1
                    elif len(fields) == 1:
                        writer.writerow(["P","","","","","","","","",float(line)])
                    elif fields[0] == "X":
                        print("STATUS",line)
                except ValueError:
                    print("IGNORED",line)
        finally:
            dev.write(b"f")
    print("RAW",raw_count,"G1",quality_count,"sequence_gaps",gaps, "CSV",a.csv)

if __name__ == "__main__":
    main()
