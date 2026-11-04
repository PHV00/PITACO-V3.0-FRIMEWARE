"""Analisador PC automatico de PPG: somente bancada, NAO uso clinico.

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
MIN_WINDOW_MS = 3000       # diagnostico em tempo de execucao, sem aguardar 8 s
MIN_WINDOW_SAMPLES = 70     # ~2,8 s a 25 Hz; exige tambem 3 s reais
PERIOD_MS = 400            # recalcula ate 2,5 vezes por segundo
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
    """Calcula candidatos independentes de G1, contato e da aprovacao SQI.

    O BPM vem da periodicidade IR; a SpO2 DEMO vem de RED/IR e pode existir
    mesmo sem BPM. Os alertas avaliam qualidade, mas nao sao gates de calculo.
    Condicoes matematicas (janela, amostras finitas, denominadores e dominio
    da curva DEMO) continuam necessarias. NAO e uma medida clinica.
    """
    result = dict(bpm=None, spo2=None, ratio=None, periodicity=None,
                  cross_corr=None, fs=None, warnings=[],
                  status="Aguardando janela (min. 3 s)")
    if len(rows) < MIN_WINDOW_SAMPLES or rows[-1][0] - rows[0][0] < MIN_WINDOW_MS:
        return result

    ts, reds, irs = zip(*rows)
    if not all(isinstance(v, (int, float)) and math.isfinite(v)
               for values in (ts, reds, irs) for v in values):
        result["status"] = "Amostra nao numerica/infinita"
        return result
    dts = [(b-a)/1000.0 for a, b in zip(ts, ts[1:])]
    if any(dt <= 0 or dt > 0.10 for dt in dts):
        result["status"] = "Intervalo de amostragem irregular"
        return result
    fs = 1.0 / statistics.median(dts)
    result["fs"] = round(fs, 2)
    effective_fs = (len(rows)-1) / ((ts[-1]-ts[0])/1000.0)
    if not 20 <= fs <= 30 or abs(effective_fs - fs) > 2:
        result["status"] = "Taxa de amostragem insuficiente"
        return result

    # Amostras fora da faixa ADC e DC nulo nao permitem razao de razoes.
    if (min(reds) < 0 or min(irs) < 0 or
            max(reds) > ADC_MAX or max(irs) > ADC_MAX):
        result["status"] = "Amostras ADC fora da escala"
        return result
    red_dc, ir_dc = statistics.fmean(reds), statistics.fmean(irs)
    if red_dc <= 0 or ir_dc <= 0:
        result["status"] = "DC optico nulo: razao indefinida"
        return result

    warnings = result["warnings"]
    if red_dc < 5000 or ir_dc < 5000:
        warnings.append("DC optico baixo")
    if max(reds) >= ADC_MAX-2048 or max(irs) >= ADC_MAX-2048:
        warnings.append("Proximo da saturacao ADC")
    if ((max(reds)-min(reds))/red_dc > .12 or
            (max(irs)-min(irs))/ir_dc > .12):
        warnings.append("Variacao optica ampla (possivel movimento)")

    red_ac = _ac_signal(reds, max(3, round(fs/2)))
    ir_ac = _ac_signal(irs, max(3, round(fs/2)))
    red_rms, ir_rms = _rms(red_ac), _rms(ir_ac)
    if red_rms/red_dc < 0.0002:
        warnings.append("AC RED baixa")
    if ir_rms/ir_dc < 0.0002:
        warnings.append("AC IR baixa")

    # BPM e SpO2 independentes: ausencia de periodicidade NAO bloqueia R.
    if ir_rms > 1e-9:
        bpm, periodicity = _acf_bpm(ir_ac, fs)
        result["bpm"] = bpm
        result["periodicity"] = round(periodicity, 3)
    if result["bpm"] is None:
        warnings.append("IR sem periodicidade BPM suficiente")

    if red_rms > 1e-9 and ir_rms > 1e-9:
        red_mu, ir_mu = statistics.fmean(red_ac), statistics.fmean(ir_ac)
        red_centered = [x-red_mu for x in red_ac]
        ir_centered = [x-ir_mu for x in ir_ac]
        cross = sum(x*y for x,y in zip(red_centered, ir_centered))
        denom = math.sqrt(sum(x*x for x in red_centered) *
                          sum(y*y for y in ir_centered))
        corr = cross/denom if denom else 0.0
        result["cross_corr"] = round(corr, 3)
        if corr < .7:
            warnings.append("Baixa coerencia RED/IR")

        ratio = (red_rms/red_dc) / (ir_rms/ir_dc)
        result["ratio"] = round(ratio, 4)
        if .2 <= ratio <= 1.4:
            # Curva de exemplo Maxim/SparkFun: DEMO, nunca calibracao PITACO.
            demo = -45.060 * ratio**2 + 30.354 * ratio + 94.845
            if 70 <= demo <= 100:
                result["spo2"] = round(demo, 1)
            else:
                warnings.append("SpO2 fora da faixa da curva DEMO")
        else:
            warnings.append("Indice R fora do dominio DEMO")
    else:
        warnings.append("R indefinido: AC RED ou IR nula")

    if result["bpm"] is not None or result["spo2"] is not None:
        result["status"] = "DEMONSTRACAO NAO VALIDADA"
    else:
        result["status"] = "Sem estimativa matematica (ver qualidade)"
    return result


class ExperimentalPpgAnalyzer:
    """Analisador automatico de bancada; qualidade separada da estimativa."""

    def __init__(self):
        self.rows = deque(maxlen=300)
        self.bpm_history = deque(maxlen=300)
        self.spo2_history = deque(maxlen=300)
        self.last_calc_ms = None
        self.last_contact = None
        self._window_ok = False
        self.result = self._empty()

    def _empty(self, status="Aguardando sinal / contato"):
        return dict(bpm=None, spo2=None, ratio=None, periodicity=None,
                    cross_corr=None, fs=None, warnings=[], status=status,
                    quality=dict(g1=None, contact=None, warnings=[]))

    def reset(self):
        """Somente no inicio de nova sessao explicita; nunca por G1 ruim."""
        self.rows.clear()
        self.bpm_history.clear()
        self.spo2_history.clear()
        self.last_calc_ms = None
        self.last_contact = None
        self._window_ok = False
        self.result = self._empty()

    def _mark_break(self, t_ms, status, contact, g1):
        """Quebra a janela de calculo, NAO apaga series ja calculadas."""
        self.rows.clear()
        self.last_calc_ms = None
        self.result = self._empty(status)
        self.result["quality"] = dict(
            g1=g1, contact=contact, warnings=[status])
        # Uma unica lacuna por interrupcao: nao inundar o historico com
        # None por cada amostra de sinal ruim.
        if self._window_ok and isinstance(t_ms, (int, float)) and math.isfinite(t_ms):
            self.bpm_history.append((t_ms/1000.0, None))
            self.spo2_history.append((t_ms/1000.0, None))
        self._window_ok = False

    def observe(self, msg, gap=False):
        if msg.get("type") != "sample":
            return
        t_ms = msg.get("t_ms")
        ppg = msg.get("ppg") or {}
        sqi = msg.get("sqi") or {}
        red, ir = ppg.get("red"), ppg.get("ir")
        contact, g1 = sqi.get("contact"), sqi.get("g1")
        numeric = (all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in (t_ms, red, ir))
                   and 0 <= red <= ADC_MAX and 0 <= ir <= ADC_MAX)
        transition = (self.last_contact is not None and
                      contact is not self.last_contact)
        self.last_contact = contact
        irregular = bool(self.rows and
                         (t_ms <= self.rows[-1][0] or
                          t_ms-self.rows[-1][0] > 100)) if numeric else False

        if gap or not numeric or irregular or transition:
            reason = ("Gap de sequencia/timestamp" if gap or irregular else
                      "Amostra fora da escala" if not numeric else
                      "Transicao de contato")
            self._mark_break(t_ms, reason, contact, g1)
            if gap or not numeric or transition:
                return

        # O contato e o G1 sao apenas etiquetas de qualidade. A coleta
        # experimental prossegue ate com G1 reprovado ou contato ausente.
        self.rows.append((t_ms, red, ir))
        self._window_ok = True
        while self.rows and t_ms-self.rows[0][0] > WINDOW_MS:
            self.rows.popleft()

        if self.last_calc_ms is None or t_ms-self.last_calc_ms >= PERIOD_MS:
            self.last_calc_ms = t_ms
            self.result = estimate_experimental(list(self.rows))
            self.bpm_history.append((t_ms/1000.0, self.result["bpm"]))
            self.spo2_history.append((t_ms/1000.0, self.result["spo2"]))

        # Qualidade NAO interfere nos resultados numericos. Expor cada
        # criterio separadamente para comparar estimativas com/sem G1.
        flags = list(self.result["warnings"])
        if contact is not True:
            flags.insert(0, "Contato ausente/desconhecido")
        if g1 is not True:
            flags.insert(0, "G1 reprovado" if g1 is False else "G1 pendente")
        self.result["quality"] = dict(
            g1=g1, contact=contact, warnings=flags)

    def snapshot(self):
        return dict(self.result, enabled=True,
                    warnings=list(self.result["warnings"]),
                    quality=dict(self.result["quality"],
                                 warnings=list(self.result["quality"]["warnings"])),
                    bpm_history=list(self.bpm_history),
                    spo2_history=list(self.spo2_history))
