"""Analisador PC opcional de PPG: somente bancada, NAO uso clinico.

RED/IR RAW do MAX30102 a ~25 Hz. BPM por periodicidade (IR);
SpO2 ilustrativa pelo indice R=(ACred/DCred)/(ACir/DCir) e curva DEMO
do algoritmo Maxim/SparkFun. A curva NAO e calibracao do PITACO, portanto
o numero jamais deve ir para Unity ou ser considerado oximetria validada.
Sem numpy/scipy: nao altera dependencias do middleware legado.
"""
import math
import statistics
from collections import deque


MIN_BPM = 35
MAX_BPM = 200
WINDOW_MS = 8000
MIN_WINDOW_MS = 7500
PERIOD_MS = 1000
ADC_MAX = 262143


def _rms(values):
    return math.sqrt(sum(x * x for x in values) / len(values))


def _ac_signal(values, half_width):
    """Remocao da componente lenta via media movel + suavizacao de 3 pontos."""
    pref = [0.0]
    for x in values:
        pref.append(pref[-1] + x)
    n = len(values)
    high = []
    for i, value in enumerate(values):
        lo, hi = max(0, i - half_width), min(n, i + half_width + 1)
        high.append(value - (pref[hi] - pref[lo]) / (hi - lo))
    return [(high[max(i - 1, 0)] + high[i] + high[min(i + 1, n - 1)])
            / 3.0 for i in range(n)]


def _acf_bpm(ir_ac, fs):
    """Autocorrelacao normalizada, minimo de 0.57 e periodos 35..200 bpm."""
    y_mean = statistics.fmean(ir_ac)
    y = [v - y_mean for v in ir_ac]
    low = max(2, int(fs * 60 / MAX_BPM))
    high = min(len(y) // 3, int(fs * 60 / MIN_BPM) + 1)
    scores = {}
    for lag in range(low, high + 1):
        a, b = y[:-lag], y[lag:]
        energy = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
        scores[lag] = sum(x*z for x, z in zip(a, b)) / energy if energy else 0.0
    if not scores:
        return None, 0.0
    best = max(scores.values())
    if best < 0.57:
        return None, best
    # O menor pico semelhante ao melhor evita selecionar o segundo ciclo.
    candidates = [lag for lag in scores
                  if scores[lag] >= best - 0.075
                  and scores[lag] >= scores.get(lag-1, -1)
                  and scores[lag] >= scores.get(lag+1, -1)]
    if not candidates:
        return None, best
    lag = min(candidates)
    # Interpolacao parabólica da autocorrelacao para evitar BPM em degraus.
    left, center, right = scores.get(lag-1), scores[lag], scores.get(lag+1)
    refined = float(lag)
    if left is not None and right is not None:
        denom = left - 2*center + right
        if denom < -1e-8:
            correction = 0.5 * (left-right) / denom
            refined += max(-0.5, min(0.5, correction))
    bpm = 60.0 * fs / refined
    return (round(bpm, 1) if MIN_BPM <= bpm <= MAX_BPM else None), best


def estimate_experimental(rows):
    """Recebe tuplas (t_ms,red,ir) consecutivas e retorna diagnostico isolado.

    Rejeita falta de continuidade, baixa perfusao optica aparente,
    artefatos de movimento grossos e pulsos nao periodicos.
    Este e um prototipo para comparar com referencias, NAO um SQI clinico.
    """
    result = dict(bpm=None, spo2=None, ratio=None, periodicity=None,
                  cross_corr=None, fs=None, status="Aguardando janela")
    if len(rows) < 160 or rows[-1][0] - rows[0][0] < MIN_WINDOW_MS:
        return result
    ts, reds, irs = zip(*rows)
    dts = [(b-a)/1000.0 for a,b in zip(ts, ts[1:])]
    if any(dt <= 0 or dt > 0.10 for dt in dts):
        result["status"] = "Intervalo de amostragem irregular"
        return result
    fs = 1.0 / statistics.median(dts)
    result["fs"] = round(fs, 2)
    if not 20 <= fs <= 30 or abs((len(rows)-1)/(ts[-1]-ts[0])*1000 - fs) > 2:
        result["status"] = "Taxa de amostragem insuficiente"
        return result
    red_dc, ir_dc = statistics.fmean(reds), statistics.fmean(irs)
    if red_dc < 5000 or ir_dc < 5000 or max(reds) > ADC_MAX-2048 or max(irs) > ADC_MAX-2048:
        result["status"] = "Sem sinal optico util"
        return result
    # Variação acima de 12% do DC nesta janela e indicio de movimento/retirada.
    if ((max(reds)-min(reds))/red_dc > .12 or
            (max(irs)-min(irs))/ir_dc > .12):
        result["status"] = "Artefato optico amplo"
        return result
    red_ac = _ac_signal(reds, max(3, round(fs/2)))
    ir_ac = _ac_signal(irs, max(3, round(fs/2)))
    red_rms, ir_rms = _rms(red_ac), _rms(ir_ac)
    if red_rms/red_dc < 0.0002 or ir_rms/ir_dc < 0.0002:
        result["status"] = "AC pulsátil muito baixa"
        return result
    bpm, periodicity = _acf_bpm(ir_ac, fs)
    result["periodicity"] = round(periodicity, 3)
    if bpm is None:
        result["status"] = "Batimentos nao periodicos"
        return result
    result["bpm"] = bpm

    red_mu, ir_mu = statistics.fmean(red_ac), statistics.fmean(ir_ac)
    red_centered = [x-red_mu for x in red_ac]
    ir_centered = [x-ir_mu for x in ir_ac]
    cross = sum(x*y for x,y in zip(red_centered, ir_centered))
    denom = math.sqrt(sum(x*x for x in red_centered) *
                      sum(y*y for y in ir_centered))
    cross_corr = cross/denom if denom else 0.0
    result["cross_corr"] = round(cross_corr, 3)
    if cross_corr < 0.7:
        result["status"] = "BPM exp; RED/IR incoerentes para R"
        return result

    ratio = (red_rms/red_dc) / (ir_rms/ir_dc)
    result["ratio"] = round(ratio, 4)
    if not 0.2 <= ratio <= 1.4:
        result["status"] = "BPM exp; indice R fora do dominio demo"
        return result
    # Curva demonstrativa do exemplo Maxim/SparkFun, NAO calibracao do PITACO.
    value = -45.060 * ratio**2 + 30.354 * ratio + 94.845
    if not 70 <= value <= 100:
        result["status"] = "BPM exp; SpO2 demo fora do dominio"
        return result
    result["spo2"] = round(value, 1)
    result["status"] = "DEMONSTRACAO NAO VALIDADA"
    return result


class ExperimentalPpgAnalyzer:
    """Um analisador por sessao, desligado por padrao e independente da Unity."""
    def __init__(self):
        self.enabled = False
        self.rows = deque(maxlen=300)
        self.bpm_history = deque(maxlen=300)
        self.spo2_history = deque(maxlen=300)
        self.last_calc_ms = None
        self.result = self._empty()

    def _empty(self, status="Desligado"):
        return dict(bpm=None, spo2=None, ratio=None, periodicity=None,
                    cross_corr=None, fs=None, status=status)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.reset()

    def reset(self):
        self.rows.clear()
        self.bpm_history.clear()
        self.spo2_history.clear()
        self.last_calc_ms = None
        self.result = self._empty("Aguardando G1 + contato" if self.enabled
                                  else "Desligado")

    def observe(self, msg, gap=False):
        if not self.enabled or msg.get("type") != "sample":
            return
        t_ms = msg.get("t_ms")
        ppg = msg.get("ppg") or {}
        sqi = msg.get("sqi") or {}
        red, ir = ppg.get("red"), ppg.get("ir")
        good = (sqi.get("contact") is True and sqi.get("g1") is True
                and isinstance(t_ms, (int, float))
                and isinstance(red, (int, float)) and isinstance(ir, (int, float))
                and all(math.isfinite(v) for v in (t_ms, red, ir))
                and 5000 <= red < ADC_MAX-2048
                and 5000 <= ir < ADC_MAX-2048)
        if gap or not good or (self.rows and
                (t_ms <= self.rows[-1][0] or t_ms-self.rows[-1][0] > 100)):
            self.rows.clear()
            self.last_calc_ms = None
            self.result = self._empty("G1/contato/gap: sem estimativa")
            if isinstance(t_ms, (int, float)):
                self.bpm_history.append((t_ms/1000.0, None))
                self.spo2_history.append((t_ms/1000.0, None))
            if not good or gap:
                return
        self.rows.append((t_ms, red, ir))
        while self.rows and t_ms-self.rows[0][0] > WINDOW_MS:
            self.rows.popleft()
        if self.last_calc_ms is None or t_ms-self.last_calc_ms >= PERIOD_MS:
            self.last_calc_ms = t_ms
            self.result = estimate_experimental(list(self.rows))
            self.bpm_history.append((t_ms/1000.0, self.result["bpm"]))
            self.spo2_history.append((t_ms/1000.0, self.result["spo2"]))

    def snapshot(self):
        return dict(self.result, enabled=self.enabled,
                    bpm_history=list(self.bpm_history),
                    spo2_history=list(self.spo2_history))
