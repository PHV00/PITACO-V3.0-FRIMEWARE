"""Modelo independente da UI para testar o transporte PPG do PITACO 2.4.

Recebe dicionarios interpretados pelo pitaco24_protocol. NAO modifica RAW,
o firmware, os thresholds G1 ou os comandos BLE/USB/OTA existentes.
Amostras reprovadas e de contato ausente permanecem no historico e no CSV.
"""
import csv
import math
import queue
import threading
import time
from collections import deque

from .experimental import ExperimentalPpgAnalyzer


CSV_FIELDS = (
    "type", "transport", "rx_s", "seq", "window", "t_ms", "red", "ir",
    "bpm", "bpm_valid", "pressure_pa", "g1", "reason", "samples", "contact"
)
_STOP = object()

MEAN_WINDOW_S = 60.0


def _rolling_mean_by_seconds(series, latest_s, segment_start_s, window_s=MEAN_WINDOW_S):
    """Media por segundo das estimativas exibiveis, sem peso extra por pacotes.

    Nao faz media de RED/IR. Cada segundo com uma ou mais leituras validas
    contribui uma vez. Retorna cobertura para mostrar PARCIAL quando faltam
    dados; nao inventa estimativas entre lacunas.
    """
    result = dict(value=None, valid_seconds=0, status="indisponivel")
    if (segment_start_s is None or latest_s is None or
            not math.isfinite(latest_s) or not math.isfinite(segment_start_s)):
        return result
    # Nunca exceder 60 buckets, inclusive se o ultimo t for um segundo inteiro.
    oldest_bucket = int(math.floor(latest_s)) - int(window_s) + 1
    buckets = {}
    for t, v in series:
        if (not isinstance(t, (int, float)) or not math.isfinite(t) or
                t < segment_start_s or int(math.floor(t)) < oldest_bucket or
                t > latest_s or
                not isinstance(v, (int, float)) or isinstance(v, bool) or
                not math.isfinite(v)):
            continue
        key = int(math.floor(t))
        total, count = buckets.get(key, (0.0, 0))
        buckets[key] = (total+v, count+1)
    result["valid_seconds"] = len(buckets)
    if len(buckets) < 3:
        return result
    per_second = [total/count for total, count in buckets.values()]
    result["value"] = round(sum(per_second)/len(per_second), 1)
    elapsed = latest_s-segment_start_s
    result["status"] = ("completa" if elapsed >= window_s and
                        len(buckets) >= 45 else "parcial")
    return result


class PpgCsvRecorder:
    """Grava em thread dedicada para nao bloquear callbacks USB/BLE."""

    def __init__(self, max_pending=4096):
        self._lock = threading.Lock()
        self._max_pending = max_pending
        self._queue = None
        self._thread = None
        self._active = False
        self._started_at = 0.0
        self.path = None
        self.dropped = 0
        self.written = 0
        self.error = None

    @property
    def active(self):
        with self._lock:
            return self._active

    def start(self, path):
        if not path:
            raise ValueError("Caminho CSV vazio")
        with self._lock:
            if self._active or (self._thread and self._thread.is_alive()):
                raise RuntimeError("Gravacao ja iniciada ou ainda encerrando")
            q = queue.Queue(maxsize=self._max_pending)
            self._queue = q
            self.dropped = 0
            self.written = 0
            self.error = None
            self.path = str(path)
            self._started_at = time.monotonic()
            # Abrir antes de anunciar ativo, para expor erros de permissao/caminho.
            f = open(path, "w", newline="", encoding="utf-8")
            self._active = True
            thread = threading.Thread(target=self._writer, args=(q, f), daemon=True)
            self._thread = thread
            thread.start()

    def _writer(self, q, file):
        try:
            with file:
                writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
                writer.writeheader()
                while True:
                    row = q.get()
                    if row is _STOP:
                        break
                    writer.writerow(row)
                    with self._lock:
                        self.written += 1
        except Exception as exc:
            with self._lock:
                self.error = str(exc)
                self._active = False

    def record(self, msg, source, at_s):
        with self._lock:
            if not self._active:
                return
            q = self._queue
            rx_s = round(at_s - self._started_at, 6)

        kind = msg.get("type")
        ppg = msg.get("ppg") or {}
        sqi = msg.get("sqi") or {}
        pressure = msg.get("mpx5010dp") or {}
        row = {
            "type": kind, "transport": source, "rx_s": rx_s,
            "seq": msg.get("seq", ""), "window": msg.get("window", ""),
            "t_ms": msg.get("t_ms", ""),
            "red": ppg.get("red", ""), "ir": ppg.get("ir", ""),
            "bpm": ppg.get("bpm", ""), "bpm_valid": ppg.get("bpm_valid", ""),
            "pressure_pa": pressure.get("pressure_pa", ""),
            "g1": sqi.get("g1", ""), "reason": sqi.get("reason", ""),
            "samples": sqi.get("samples", ""), "contact": sqi.get("contact", "")
        }
        try:
            q.put_nowait(row)
        except queue.Full:
            with self._lock:
                self.dropped += 1

    def stop(self):
        with self._lock:
            if not self._active and not (self._thread and self._thread.is_alive()):
                return
            self._active = False
            q, thread = self._queue, self._thread
        # A sentinela precisa ser enfileirada depois das linhas pendentes.
        if q is not None and thread is not None and thread.is_alive():
            q.put(_STOP)
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise RuntimeError("Gravacao CSV ainda nao finalizada")
        with self._lock:
            self._thread = None


class PpgMonitor:
    """Monitor nao clinico com telemetria USB/BLE e historico bounded."""

    def __init__(self, max_points=250):
        self._lock = threading.Lock()
        self.history = deque(maxlen=max_points)
        self.bpm_history = deque(maxlen=max_points)
        # Retencao independente da tela de 30s: a media exige 60s reais
        # de BPM do firmware, a ~25 amostras/s.
        self.bpm_mean_history = deque(maxlen=1800)
        self.recent_rx = deque(maxlen=400)
        self.csv = PpgCsvRecorder()
        self.experimental = ExperimentalPpgAnalyzer()
        self.reset()

    def reset(self):
        with self._lock:
            self.history.clear()
            self.bpm_history.clear()
            self.bpm_mean_history.clear()
            self.recent_rx.clear()
            self.experimental.reset()
            self.first_rx = None
            self.last_rx = None
            self.last_seq = None
            self.last_t_ms = None
            self.mean_segment_start_s = None  # contato continuo da sessao
            self.source = ""
            self.samples = 0
            self.missing = 0
            self.duplicates = 0
            self.seq_resets = 0
            self.invalid_json = 0
            self.ble_fragments = 0
            self.pressure_messages = 0
            self.g1_windows = 0
            self.g1_passes = 0
            self.g1_failures = 0
            self.g1_reason = None
            self.g1_samples = None
            self.g1_window = None
            self.contact = None
            self.g1_effective = None
            self.reason = None
            self.bpm = None
            self.fw_bpm_status = "Aguardando leitura PPG"

    def note_ble_fragment(self):
        with self._lock:
            self.ble_fragments += 1

    def note_invalid_json(self):
        with self._lock:
            self.invalid_json += 1

    def observe(self, msg, source, now=None):
        """Observa evento recebido no PC; nao supoe amostras ausentes."""
        now = time.monotonic() if now is None else now
        kind = msg.get("type")
        if kind not in ("sample", "g1", "pressure"):
            return
        with self._lock:
            self.source = source
            if kind == "pressure":
                self.pressure_messages += 1
            elif kind == "g1":
                self.g1_windows += 1
                sqi = msg.get("sqi") or {}
                self.g1_reason = sqi.get("reason")
                self.g1_samples = sqi.get("samples")
                self.g1_window = msg.get("window")
                if sqi.get("g1") is True:
                    self.g1_passes += 1
                elif sqi.get("g1") is False:
                    self.g1_failures += 1
            else:
                seq = msg["seq"]
                t_ms = msg.get("t_ms")
                previous_rx = self.last_rx
                previous_t_ms = self.last_t_ms
                previous_contact = self.contact
                ppg = msg["ppg"]
                sqi = msg.get("sqi") or {}
                sequence_gap = False
                if self.last_seq is not None:
                    delta = (seq - self.last_seq) & 0xFFFF
                    sequence_gap = delta != 1
                    if delta == 0:
                        self.duplicates += 1
                    elif 0 < delta < 32768:
                        if delta > 1:
                            self.missing += delta - 1
                            # Quebrar linha PPG; nao interpolar dado que nao chegou.
                            if isinstance(t_ms, (int, float)):
                                self.history.append((t_ms / 1000.0 - .02, None, None))
                        self.last_seq = seq
                    else:
                        # Seq retrocedeu; detectar reinicio, nao inflar perdas.
                        self.seq_resets += 1
                        self.history.clear()
                        self.bpm_history.clear()
                        self.bpm_mean_history.clear()
                        self.recent_rx.clear()
                        self.mean_segment_start_s = None
                        self.last_seq = seq
                else:
                    self.last_seq = seq
                self.last_t_ms = t_ms
                self.last_rx = now
                if self.first_rx is None:
                    self.first_rx = now
                self.samples += 1
                self.recent_rx.append(now)
                while self.recent_rx and now - self.recent_rx[0] > 10.0:
                    self.recent_rx.popleft()
                sample_t = (t_ms / 1000.0 if isinstance(t_ms, (int, float))
                            else self.samples / 25.0)
                self.history.append((sample_t, ppg["red"], ppg["ir"]))
                self.contact = sqi.get("contact")
                # Media atual exige contato continuo; o historico completo
                # permanece para analise, mas NUNCA mistura duas colocacoes
                # do dedo, reconexoes, ou um relogio reiniciado.
                if self.contact is not True:
                    self.mean_segment_start_s = None
                elif (self.mean_segment_start_s is None or
                      previous_contact is not True or
                      (previous_rx is not None and now-previous_rx >= 2.0) or
                      (isinstance(t_ms, (int, float)) and
                       isinstance(previous_t_ms, (int, float)) and
                       t_ms < previous_t_ms)):
                    self.mean_segment_start_s = sample_t
                self.g1_effective = sqi.get("g1")
                self.reason = sqi.get("reason")
                measured_bpm = ppg.get("bpm")
                # O painel nao apresenta BPM se o firmware reprova contato/G1.
                accepted_bpm = (
                    measured_bpm if ppg.get("bpm_valid") is True
                    and sqi.get("g1") is True and self.contact is not False
                    and isinstance(measured_bpm, (int, float))
                    and not isinstance(measured_bpm, bool)
                    and 35 <= measured_bpm <= 200
                    else None
                )
                self.bpm = accepted_bpm
                if self.contact is False:
                    self.fw_bpm_status = "Sem contato"
                elif sqi.get("g1") is not True:
                    self.fw_bpm_status = ("G1 reprovado" if sqi.get("g1") is False
                                          else "Aguardando G1")
                elif ppg.get("bpm_valid") is not True:
                    self.fw_bpm_status = "Firmware ainda sem BPM valido"
                elif accepted_bpm is None:
                    self.fw_bpm_status = "BPM recebido fora de 35-200"
                else:
                    self.fw_bpm_status = "BPM firmware valido"
                self.bpm_history.append((sample_t, accepted_bpm))
                self.bpm_mean_history.append((sample_t, accepted_bpm))
                self.experimental.observe(msg, gap=sequence_gap)
        self.csv.record(msg, source, now)

    def snapshot(self, now=None):
        """Copia valores para a thread principal do Tk sem tocar na UI."""
        now = time.monotonic() if now is None else now
        with self._lock:
            rx = list(self.recent_rx)
            sample_age = now - self.last_rx if self.last_rx is not None else None
            if rx and sample_age is not None and sample_age < 2.0:
                rate = (len(rx) - 1) / (rx[-1] - rx[0]) if len(rx) > 1 and rx[-1] > rx[0] else 0.0
            else:
                rate = 0.0
            # Quatro campos: duas leituras atuais e duas medias separadas.
            # As medias nao usam diretamente as contagens opticas e nao
            # incorporam candidatos sem contato do diagnostico Python.
            latest_s = (self.last_t_ms/1000.0
                        if isinstance(self.last_t_ms, (int, float)) else None)
            segment = self.mean_segment_start_s if self.contact is True else None
            fw_mean = _rolling_mean_by_seconds(
                self.bpm_mean_history, latest_s, segment)
            py_mean = _rolling_mean_by_seconds(
                self.experimental.bpm_history, latest_s, segment)
            spo2_mean = _rolling_mean_by_seconds(
                self.experimental.spo2_history, latest_s, segment)
            out = {
                "mean60": dict(bpm_fw=fw_mean, bpm_py=py_mean,
                               spo2=spo2_mean),
                "history": list(self.history), "bpm_history": list(self.bpm_history), "sample_rate": rate,
                "sample_age_s": sample_age,
                "samples": self.samples, "missing": self.missing,
                "duplicates": self.duplicates, "seq_resets": self.seq_resets,
                "ble_fragments": self.ble_fragments,
                "invalid_json": self.invalid_json,
                "pressure_messages": self.pressure_messages,
                "g1_windows": self.g1_windows, "g1_passes": self.g1_passes,
                "g1_failures": self.g1_failures, "g1_reason": self.g1_reason,
                "g1_samples": self.g1_samples, "g1_window": self.g1_window,
                "contact": self.contact, "g1_effective": self.g1_effective,
                "reason": self.reason, "bpm": self.bpm,
                "fw_bpm_status": self.fw_bpm_status,
                "source": self.source,
                "experimental": self.experimental.snapshot()
            }
        if sample_age is None or sample_age >= 2.0:
            out["bpm"] = None
            out["fw_bpm_status"] = "Sem amostras recentes"
            for metric in out["mean60"].values():
                metric.update(value=None, status="indisponivel")
        # Telemetria interrompida nao pode manter valores experimentais atuais.
        # Historicos ficam disponiveis para diagnostico (nenhum RAW apagado).
        if sample_age is None or sample_age >= 2.0:
            out["experimental"].update(
                bpm=None, spo2=None, ratio=None,
                status="Sem amostras recentes")
        out["csv_active"] = self.csv.active
        out["csv_written"] = self.csv.written
        out["csv_dropped"] = self.csv.dropped
        out["csv_error"] = self.csv.error
        return out
