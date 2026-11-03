"""Recebimento e roteamento de linhas PITACO 2.4 (USB e PPG BLE).

Responsabilidades:
  * decodificar JSONL/pressao antiga sem Tk, Bleak ou COM reais;
  * manter a contagem de notificacoes, erros e amostras RAW no monitor;
  * atualizar pressao somente no canal que a permite;
  * repassar BPM firmware qualificado para a COM virtual, no maximo 1/s;
  * nunca encaminhar SpO2 experimental ou amostras inventadas a Unity.

As funcoes de IO (atualizacao de pneumo, COM virtual e log) sao injetadas
pelo GUI; isso permite testes com callbacks falsos.
"""
import math
import time

from .protocol import BleJsonlBuffer, parse_pitaco_line


class PitacoMessageRouter:
    """Traduz frames em eventos; nao importa bibliotecas de hardware ou UI."""

    def __init__(self, monitor, on_pressure, can_send_bpm, send_bpm,
                 report_error=None, clock=None):
        self.monitor = monitor
        self.on_pressure = on_pressure
        self.can_send_bpm = can_send_bpm
        self.send_bpm = send_bpm
        self.report_error = report_error or (lambda _text: None)
        self.clock = clock or time.monotonic
        self.ble_ppg_lines = BleJsonlBuffer()
        self.last_oxi_sent = 0.0

    def reset_ble(self):
        """Invalida fragmentos pendentes ao iniciar/reiniciar conexao BLE."""
        self.ble_ppg_lines.reset()

    def reset_session(self):
        """Elimina estado do transporte ao iniciar nova sessao."""
        self.reset_ble()
        self.last_oxi_sent = 0.0

    def process_line(self, line_str, allow_pressure=True, source="USB"):
        """Processa uma linha completa sem ocultar amostras recusadas por SQI."""
        msg = parse_pitaco_line(line_str)
        if msg is None:
            return False

        kind = msg.get("type")
        self.monitor.observe(msg, source=source)
        if kind == "pressure":
            if allow_pressure:
                self.on_pressure(msg["mpx5010dp"]["pressure_pa"])
            return True
        if kind == "g1":
            return True
        if kind != "sample":
            return False

        pressure = msg.get("mpx5010dp")
        if allow_pressure and isinstance(pressure, dict) and pressure.get("valid") is True:
            pa = pressure.get("pressure_pa")
            if (isinstance(pa, (float, int)) and not isinstance(pa, bool)
                    and math.isfinite(pa)):
                self.on_pressure(float(pa))

        ppg = msg.get("ppg")
        sqi = msg.get("sqi")
        if not isinstance(ppg, dict) or not isinstance(sqi, dict):
            return True
        bpm = ppg.get("bpm")
        # Contrato da COM original: 'FC,SpO2', onde 0 significa INDISPONIVEL.
        # A estimativa experimental Python NAO participa desta transmissao.
        if (ppg.get("bpm_valid") is True and sqi.get("g1") is True
                and isinstance(bpm, (int, float)) and not isinstance(bpm, bool)
                and math.isfinite(bpm) and 35 <= bpm <= 200
                and self.can_send_bpm()
                and self.clock() - self.last_oxi_sent >= 1.0):
            try:
                self.send_bpm(round(bpm))
                self.last_oxi_sent = self.clock()
            except Exception as exc:
                self.report_error(f"Falha no envio de BPM para Unity: {exc}")
        return True

    def feed_ble_ppg(self, fragment):
        """Notificacoes BLE podem conter apenas parte de um frame JSONL.

        Retorna quantidade de linhas completas recebidas nesta notificacao.
        Fragmentos e frames invalidos contam nos diagnosticos do monitor.
        """
        self.monitor.note_ble_fragment()
        lines = self.ble_ppg_lines.feed(bytes(fragment))
        for line_str in lines:
            try:
                if not self.process_line(line_str, allow_pressure=False, source="BLE"):
                    self.monitor.note_invalid_json()
            except Exception as exc:
                self.monitor.note_invalid_json()
                self.report_error(f"Erro ao interpretar JSON PPG BLE: {exc}")
        return len(lines)
