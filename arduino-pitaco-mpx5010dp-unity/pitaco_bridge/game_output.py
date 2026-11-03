"""Contrato de saida do middleware para um unico receptor serial Unity.

Nao confundir transporte ESP32->Python (USB/BLE, JSON) com Python->Unity
(COM virtual do PITACO). O formato legado numerico permanece identico.

Modo opt-in P24:
    P24,<valor_respiratorio_Pa>,<bpm_ou_vazio>,<spo2_vazio>,<g1>,<contato>\r\n

O campo SpO2 fica deliberadamente VAZIO: o prototipo Python nao esta
calibrado. A falta de BPM nunca vira 0 bpm. Campos g1/contato so podem
ser 1 se a telemetria e recente (menos de 2 s).
"""
import math

GAME_OUTPUT_PRESSURE = "Pressão relativa (Pa)"
GAME_OUTPUT_FLOW = "Fluxo estimado (L/min)"
GAME_OUTPUT_COMBO = "PITACO 2.4 Combo"


def build_game_frame(respiratory_value, mode, monitor_snapshot=None):
    """Retorna bytes ASCII terminados em CRLF para COM virtual do jogo.

    Preserva a mesma precisao e cadencia do fluxo legado; modo combinado
    tem prefixo para permitir parser nao ambiguo no SerialControllerPitaco.
    """
    value = float(respiratory_value)
    if not math.isfinite(value):
        raise ValueError("Grandeza respiratoria nao finita")

    legacy = f"{value:.2f}"
    if mode != GAME_OUTPUT_COMBO:
        return (legacy + "\r\n").encode("ascii")

    snap = monitor_snapshot or {}
    age = snap.get("sample_age_s")
    recent = (isinstance(age, (int, float)) and not isinstance(age, bool)
              and math.isfinite(age) and 0 <= age < 2.0)
    contact = bool(recent and snap.get("contact") is True)
    g1 = bool(recent and snap.get("g1_effective") is True)
    bpm = snap.get("bpm")
    valid_bpm = (contact and g1 and isinstance(bpm, (int, float))
                 and not isinstance(bpm, bool) and math.isfinite(bpm)
                 and 35 <= bpm <= 200)
    bpm_field = f"{bpm:.1f}" if valid_bpm else ""
    # 3. campo apos BPM reservado a SpO2, intencionalmente vazio.
    return (f"P24,{legacy},{bpm_field},,{int(g1)},{int(contact)}\r\n").encode("ascii")
