# Modelo respiratorio original; estimativa de fluxo nao validada.
import math
from collections import deque

# Constantes para o cálculo de fluxo (Modelo Físico de Placa de Orifício / Bernoulli)
PITACO_RADIUS = 0.018                      # Raio do tubo principal (m) = 18mm
PITACO_ORIFICE_RADIUS = PITACO_RADIUS / 2.0 # Raio do orifício de restrição (m) = 9mm
AIR_DENSITY = 1.204                         # Densidade do ar a 20°C (kg/m³)
DISCHARGE_COEF = 0.62                      # Coeficiente de descarga do orifício padrão (Cd)

# Área da seção do orifício (m²)
ORIFICE_AREA = 3.1415926535 * (PITACO_ORIFICE_RADIUS ** 2)

# Fator base físico: Q = Cd * A * sqrt(2 * ΔP / ρ) convertido para L/min (x 60.000)
BASE_ORIFICE_FACTOR = DISCHARGE_COEF * ORIFICE_AREA * math.sqrt(2.0 / AIR_DENSITY) * 60000.0

flow_multiplier = 5.0

# Firmware MPX5010DP faz ADC -> Volts -> Pa. NAO recalcular a tensao aqui.
# Fluxo L/min abaixo e estimado por modelo de orificio, NAO validado.
def parse_pressure_pa(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Leitura de pressao nao finita")
    return value

def calculate_flow(pressure_pa):
    if abs(pressure_pa) < 1e-4:
        return 0.0
    sign = 1.0 if pressure_pa >= 0 else -1.0
    abs_pa = abs(pressure_pa)
    # Modelo quadrático do orifício: Q ∝ sqrt(ΔP)
    flow_lmin = sign * BASE_ORIFICE_FACTOR * math.sqrt(abs_pa) * (flow_multiplier / 5.0)
    return flow_lmin

def flow_to_pressure(flow_lmin):
    if abs(flow_lmin) < 1e-4:
        return 0.0
    effective_factor = BASE_ORIFICE_FACTOR * (flow_multiplier / 5.0)
    if effective_factor == 0:
        return 0.0
    sign = 1.0 if flow_lmin >= 0 else -1.0
    abs_flow = abs(flow_lmin)
    return sign * ((abs_flow / effective_factor) ** 2)

# --- CLASSE DE FILTRAGEM DE PICOS DE PRESSÃO E FLUXO ---
class PressureFilter:
    def __init__(self, mode="Moderado"):
        self.mode = mode
        self.median_buffer = deque(maxlen=5)
        self.ema_value = 0.0
        self.ema_initialized = False

    def set_mode(self, mode):
        self.mode = mode
        self.reset()

    def reset(self):
        self.median_buffer.clear()
        self.ema_value = 0.0
        self.ema_initialized = False

    def process(self, raw_flow):
        if self.mode == "Desativado":
            return raw_flow

        if self.mode == "Suave":
            median_size = 3
            base_deadband_pa = 12.0
            alpha = 0.95
        elif self.mode == "Moderado":
            median_size = 5
            base_deadband_pa = 16.0  # Limiar em Pa ligeiramente acima da borda de 15 Pa do ESP
            alpha = 0.90
        else:  # Agressivo
            median_size = 5
            base_deadband_pa = 20.0
            alpha = 0.85

        # O limiar de corte em L/min escala dinamicamente com o multiplicador de fluxo selecionado
        deadband_flow = calculate_flow(base_deadband_pa)

        if self.median_buffer.maxlen != median_size:
            self.median_buffer = deque(self.median_buffer, maxlen=median_size)

        # 1. Filtro de Mediana diretamente sobre o FLUXO (elimina 100% dos picos/glitches de 1-2 amostras)
        self.median_buffer.append(raw_flow)
        sorted_samples = sorted(self.median_buffer)
        med_flow = sorted_samples[len(sorted_samples) // 2]

        # 2. Deadband em fluxo que acompanha a escala de fluxo (zera o ruído perto de zero em qualquer escala)
        if abs(med_flow) < deadband_flow:
            med_flow = 0.0

        # 3. Média Móvel Exponencial (EMA)
        if not self.ema_initialized:
            self.ema_value = med_flow
            self.ema_initialized = True
        else:
            self.ema_value = alpha * med_flow + (1.0 - alpha) * self.ema_value

        if abs(self.ema_value) < 1.0:
            self.ema_value = 0.0

        return self.ema_value
