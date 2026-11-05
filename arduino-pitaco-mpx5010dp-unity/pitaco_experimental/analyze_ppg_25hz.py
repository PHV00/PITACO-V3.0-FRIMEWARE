#!/usr/bin/env python3
"""Audita CSV de bancada sem alterar o firmware ou a GUI do PITACO."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pitaco_bridge.ppg_validation_25hz import (DEFAULT_THRESHOLDS, analyze_capture,
                                                 read_capture, read_labels)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Auditoria PPG 25 Hz (nao clinica)")
    parser.add_argument("csv", help="CSV do probe ou monitor GUI")
    parser.add_argument("--thresholds", default=",".join(map(str,DEFAULT_THRESHOLDS)),
                        help="Valores ADC para comparacao, separados por virgula")
    parser.add_argument("--labels", help="CSV independente: colunas window,usable (0/1)")
    parser.add_argument("--output", help="Salvar relatorio completo em JSON")
    args = parser.parse_args(argv)
    thresholds = [int(x.strip()) for x in args.thresholds.split(",")]
    if not thresholds or any(x<=0 for x in thresholds):
        parser.error("thresholds devem ser inteiros positivos")
    data = analyze_capture(read_capture(args.csv),thresholds,
                           read_labels(args.labels) if args.labels else None)
    print(json.dumps({k:v for k,v in data.items() if k!="experimental_estimates"},
                     indent=2,ensure_ascii=False))
    if args.output:
        Path(args.output).write_text(json.dumps(data,indent=2,ensure_ascii=False),
                                     encoding="utf-8")
    return data


if __name__ == "__main__":
    main()
