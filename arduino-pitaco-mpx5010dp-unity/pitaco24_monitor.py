"""Modelo independente da UI para testar o transporte PPG do PITACO 2.4.

Recebe dicionarios interpretados pelo pitaco24_protocol. NAO modifica RAW,
o firmware, os thresholds G1 ou os comandos BLE/USB/OTA existentes.
Amostras reprovadas e de contato ausente permanecem no historico e no CSV.
"""
import csv
import queue
import threading
import time
from collections import deque


CSV_FIELDS = (
    "type", "transport", "rx_s", "seq", "window", "t_ms", "red", "ir",
    "bpm", "bpm_valid", "pressure_pa", "g1", "reason", "samples", "contact"
)
_STOP = object()


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
        self.recent_rx = deque(maxlen=400)
        self.csv = PpgCsvRecorder()
        self.reset()

    def reset(self):
        with self._lock:
            self.history.clear()
            self.recent_rx.clear()
            self.first_rx = None
            self.last_rx = None
            self.last_seq = None
            self.last_t_ms = None
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
                ppg = msg["ppg"]
                sqi = msg.get("sqi") or {}
                if self.last_seq is not None:
                    delta = (seq - self.last_seq) & 0xFFFF
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
                        self.recent_rx.clear()
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
                self.history.append((t_ms / 1000.0 if isinstance(t_ms, (int, float))
                                     else self.samples / 25.0,
                                     ppg["red"], ppg["ir"]))
                self.contact = sqi.get("contact")
                self.g1_effective = sqi.get("g1")
                self.reason = sqi.get("reason")
                self.bpm = ppg.get("bpm") if ppg.get("bpm_valid") is True else None
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
            out = {
                "history": list(self.history), "sample_rate": rate,
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
                "source": self.source
            }
        out["csv_active"] = self.csv.active
        out["csv_written"] = self.csv.written
        out["csv_dropped"] = self.csv.dropped
        out["csv_error"] = self.csv.error
        return out
