"""Analise OFFLINE do PPG PITACO 2.4 a ~25 Hz (sem decisoes clinicas).

Nao modifica amostras, SQI G1, firmware, transporte ou Unity. As janelas
sao ancoradas nos eventos reais type=g1 e no contador samples do firmware.
"""
import csv
import math
import statistics
from collections import Counter, deque

from .experimental import _ac_signal, estimate_experimental
from .sparkfun_pba_replay import replay_sparkfun

FIR_COEFFS = (172, 321, 579, 927, 1360, 1858, 2390, 2916, 3391, 3768, 4012, 4096)
DEFAULT_THRESHOLDS = (300, 400, 500, 600, 700, 1000)


def _boolean(value):
    return str(value).strip().lower() in ("true", "1")


def _integer(value):
    return int(float(value))


def read_capture(path):
    """Retorna os registros sample/g1 do CSV gerado pelo probe ou pela GUI."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"type", "t_ms", "red", "ir"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV sem colunas obrigatorias type,t_ms,red,ir")
        for row in reader:
            if row["type"] == "sample":
                try:
                    sample = {"type": "sample", "t_ms": _integer(row["t_ms"]),
                              "red": _integer(row["red"]), "ir": _integer(row["ir"]),
                              "seq": _integer(row["seq"]) if row.get("seq") else None,
                              "contact": _boolean(row.get("contact")),
                              "g1": _boolean(row.get("g1")),
                              "bpm_valid": _boolean(row.get("bpm_valid"))}
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 <= sample["red"] <= 262143 and 0 <= sample["ir"] <= 262143:
                    rows.append(sample)
            elif row["type"] == "g1":
                try:
                    rows.append({"type": "g1", "samples": _integer(row["samples"]),
                                 "reason": _integer(row["reason"]),
                                 "g1": _boolean(row.get("g1")),
                                 "t_ms": _integer(row["t_ms"])})
                except (TypeError, ValueError, OverflowError):
                    continue
    return rows


def _rms(a):
    return math.sqrt(sum(x*x for x in a)/len(a)) if a else 0.0


def _trend(times, values):
    """Variacao estimada por regressao linear ao longo da janela (ADC)."""
    t0 = times[0]
    t = [(x-t0)/1000.0 for x in times]
    mt, mv = statistics.fmean(t), statistics.fmean(values)
    den = sum((x-mt)**2 for x in t)
    slope = sum((x-mt)*(y-mv) for x,y in zip(t,values))/den if den else 0.0
    return slope * (t[-1]-t[0])


def _window_metrics(samples, window, reason, reported_count):
    t = [row["t_ms"] for row in samples]
    red = [row["red"] for row in samples]
    ir = [row["ir"] for row in samples]
    dts = [b-a for a,b in zip(t,t[1:])]
    # A presenca de N registros nao prova continuidade: verificar seq/timestamp.
    seq = [row.get("seq") for row in samples]
    seq_contiguous = (all(x is not None for x in seq) and
                      all((b-a) % 65536 == 1 for a,b in zip(seq,seq[1:])))
    timing_ok = all(0 < dt <= 100 for dt in dts)
    complete = (len(samples)==reported_count and
                seq_contiguous and timing_ok and len(samples)>0)
    fs = 1000.0/statistics.median(dts) if dts and min(dts)>0 else None
    out = {"window": window, "reason": reason, "reported_samples": reported_count,
           "captured_samples": len(samples), "complete": complete,
           "seq_contiguous": seq_contiguous, "timing_ok": timing_ok,
           "fs_hz": round(fs,3) if fs else None}
    for name,vals in (("red",red),("ir",ir)):
        dc = statistics.fmean(vals) if vals else 0.0
        raw_range = max(vals)-min(vals) if vals else 0
        trend = _trend(t,vals) if len(vals)>1 else 0.0
        # Mesma remocao de DC do analisador Python experimental; nao e G1.
        ac = _ac_signal(vals,max(3,round(fs/2))) if fs and len(vals)>8 else []
        rms = _rms(ac)
        out.update({name+"_mean":round(dc,2),name+"_range":raw_range,
                    name+"_endpoint_change":vals[-1]-vals[0] if vals else 0,
                    name+"_linear_trend":round(trend,2),
                    name+"_ac_rms":round(rms,3),
                    name+"_ac_dc":round(rms/dc,7) if dc else None})
    return out


def sparkfun_fir_gain(sample_rate_hz, bpm):
    """Modulo da resposta do FIR 23-taps do heartRate.cpp; NAO detector completo."""
    if sample_rate_hz <= 0 or bpm <= 0:
        raise ValueError("Frequencia ou BPM invalido")
    taps = list(FIR_COEFFS[:11])+[FIR_COEFFS[11]]+list(reversed(FIR_COEFFS[:11]))
    w = 2*math.pi*(bpm/60)/sample_rate_hz
    real = sum(c*math.cos(w*i) for i,c in enumerate(taps))/32768.0
    imag = sum(c*math.sin(w*i) for i,c in enumerate(taps))/32768.0
    return round(math.hypot(real,imag),5)


def threshold_sweep(windows, thresholds=DEFAULT_THRESHOLDS, labels=None):
    """Apenas criterio de range RED+IR; nao simula G1 completo nem contato."""
    results = []
    for threshold in thresholds:
        selected = [w for w in windows if w["complete"]]
        passed = {w["window"] for w in selected if
                  w["red_range"]>=threshold and w["ir_range"]>=threshold}
        result = {"threshold":int(threshold),"eligible_windows":len(selected),
                  "range_pass_windows":len(passed)}
        if labels is not None:
            paired = [(w["window"], bool(labels[w["window"]])) for w in selected
                      if w["window"] in labels]
            tp = sum(i in passed and good for i,good in paired)
            fp = sum(i in passed and not good for i,good in paired)
            fn = sum(i not in passed and good for i,good in paired)
            tn = sum(i not in passed and not good for i,good in paired)
            result["reference"] = {"tp":tp,"fp":fp,"fn":fn,"tn":tn,
                "sensitivity":round(tp/(tp+fn),3) if tp+fn else None,
                "specificity":round(tn/(tn+fp),3) if tn+fp else None}
        results.append(result)
    return results


def read_labels(path):
    """Rotulos de referencia humana/externa: window,usable (0 ou 1)."""
    labels = {}
    with open(path,newline="",encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            window, value = int(row["window"]),str(row["usable"]).strip().lower()
            if value not in ("0","1","true","false"):
                raise ValueError("usable deve ser 0/1/true/false")
            if window in labels:
                raise ValueError("window duplicada nos rotulos")
            labels[window] = value in ("1","true")
    return labels


def analyze_capture(rows, thresholds=DEFAULT_THRESHOLDS, labels=None):
    pending = []
    windows = []
    samples = []
    estimates = []
    good_recent = deque()
    next_calc_ms = None
    for item in rows:
        if item["type"] == "sample":
            samples.append(item)
            if not item["contact"]:
                pending.clear()
            else:
                pending.append(item)
            # Reproduz o pre-requisito da estimativa Python: contato e G1 efetivo.
            if not (item["contact"] and item["g1"]):
                good_recent.clear()
                next_calc_ms = None
            else:
                if good_recent and (item["t_ms"]<=good_recent[-1]["t_ms"] or
                                    item["t_ms"]-good_recent[-1]["t_ms"]>100):
                    good_recent.clear()
                    next_calc_ms = None
                good_recent.append(item)
                while good_recent and item["t_ms"]-good_recent[0]["t_ms"]>8000:
                    good_recent.popleft()
                if len(good_recent)>=160 and item["t_ms"]-good_recent[0]["t_ms"]>=7500:
                    if next_calc_ms is None or item["t_ms"] >= next_calc_ms:
                        result = estimate_experimental([(x["t_ms"],x["red"],x["ir"])
                                                        for x in good_recent])
                        estimates.append({"t_ms":item["t_ms"],"bpm":result["bpm"],
                                          "status":result["status"]})
                        next_calc_ms = item["t_ms"]+1000
        elif item["type"] == "g1":
            count = item["samples"]
            segment = pending[-count:] if count>0 else []
            windows.append(_window_metrics(segment,len(windows)+1,item["reason"],count))
            pending.clear()
    ts = [x["t_ms"] for x in samples]
    positive_dts = [b-a for a,b in zip(ts,ts[1:]) if b>a]
    return {"summary":{"sample_count":len(samples),"g1_windows":len(windows),
               "g1_pass":sum(x["reason"]==0 for x in windows),
               "firmware_bpm_valid_samples":sum(x["bpm_valid"] for x in samples),
               "median_sample_rate_hz":round(1000/statistics.median(positive_dts),3)
                 if positive_dts else None,
               "non_increasing_timestamps":sum(b<=a for a,b in zip(ts,ts[1:])),
               "experimental_8s_windows":len(estimates),
               "experimental_bpm_available":sum(x["bpm"] is not None for x in estimates),
               "experimental_status_counts":dict(Counter(x["status"] for x in estimates))},
            "windows":windows,"threshold_sweep":threshold_sweep(windows,thresholds,labels),
            "sparkfun_fir_gain":{"25hz":{str(b):sparkfun_fir_gain(25,b) for b in (60,90,120)},
                                 "100hz":{str(b):sparkfun_fir_gain(100,b) for b in (60,90,120)}},
            "sparkfun_pba_replay":replay_sparkfun(samples),
            "experimental_estimates":estimates}
