
import os
import sys
import subprocess
from tkinter import messagebox, Menu, filedialog
import customtkinter as ctk
import serial
import serial.tools.list_ports
import wmi
import pythoncom
import threading
import ctypes
import asyncio
import time
import struct
import json
from pitaco24_protocol import parse_pitaco_line, BleJsonlBuffer
from pitaco24_monitor import PpgMonitor
import tempfile
import urllib.request
import urllib.error
import esptool
from collections import deque
from bleak import BleakClient, BleakScanner
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

import datetime
import math

def get_config_path():
    appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    config_dir = os.path.join(appdata, "PITACO_Bridge")
    try:
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config_mpx5010dp.json")
    except:
        return "config_mpx5010dp.json"

DEFAULT_PROFILE_DATA = {
    "max_flow": 100.0,
    "min_flow": -100.0,
    "resp_rate": 0.0,
    "t_ins": 0.0,
    "t_exp": 0.0,
    "ie_ratio": "1:2.0",
    "last_updated": "Nunca"
}

DEFAULT_CONFIG = {
    "active_profile": "Padrão",
    "profiles": {
        "Padrão": DEFAULT_PROFILE_DATA.copy()
    },
    "com0com_installed": False,
    "conn_mode": "Cabo USB",
    "output_mode": "Pressão relativa (Pa)",
    "filter_mode": "Moderado",
    "scale_multiplier": 5.0,
    "scale_key": "5.0x",
    "game_port": "Somente monitor",
    "oximeter_game_port": "Somente monitor",
    "device_port": ""
}

def load_config():
    p = get_config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(data)

                # Garante estrutura de profiles
                if "profiles" not in cfg or not isinstance(cfg["profiles"], dict) or not cfg["profiles"]:
                    cfg["profiles"] = {"Padrão": DEFAULT_PROFILE_DATA.copy()}

                for prof_name, prof_dict in list(cfg["profiles"].items()):
                    merged_prof = DEFAULT_PROFILE_DATA.copy()
                    if isinstance(prof_dict, dict):
                        merged_prof.update(prof_dict)
                    cfg["profiles"][prof_name] = merged_prof

                if cfg.get("active_profile") not in cfg["profiles"]:
                    cfg["active_profile"] = list(cfg["profiles"].keys())[0]

                return cfg
        except Exception as e:
            print(f"Erro ao carregar config.json: {e}")
    return DEFAULT_CONFIG.copy()

config_data = load_config()
active_profile_name = config_data.get("active_profile", "Padrão")
current_prof = config_data["profiles"].get(active_profile_name, DEFAULT_PROFILE_DATA.copy())

persistent_max_flow = float(current_prof.get("max_flow", 100.0))
persistent_min_flow = float(current_prof.get("min_flow", -100.0))
persistent_resp_rate = float(current_prof.get("resp_rate", 0.0))
persistent_t_ins = float(current_prof.get("t_ins", 0.0))
persistent_t_exp = float(current_prof.get("t_exp", 0.0))
persistent_ie_ratio = str(current_prof.get("ie_ratio", "1:2.0"))
persistent_last_updated = str(current_prof.get("last_updated", "Nunca"))

def update_plot_header_labels():
    if 'profile_badge_label' in globals():
        profile_badge_label.configure(text=f"👤 Perfil: {active_profile_name}")
    if 'max_val_label' in globals():
        max_val_label.configure(text=f"Máx (Exp): +{persistent_max_flow:.2f} L/min")
    if 'min_val_label' in globals():
        min_val_label.configure(text=f"Mín (Insp): {persistent_min_flow:.2f} L/min")
    if 'rate_val_label' in globals():
        rate_val_label.configure(text=f"Taxa: {persistent_resp_rate:.0f} rpm" if persistent_resp_rate > 0 else "Taxa: -- rpm")
    if 'timing_val_label' in globals():
        if persistent_t_ins > 0 and persistent_t_exp > 0:
            timing_val_label.configure(text=f"Ins: {persistent_t_ins:.1f}s | Exp: {persistent_t_exp:.1f}s | I:E {persistent_ie_ratio}")
        else:
            timing_val_label.configure(text="Tempos Ins/Exp: --")

def update_active_profile_metrics(max_f=None, min_f=None, rate=None, t_in=None, t_ex=None, ie=None):
    global persistent_max_flow, persistent_min_flow, persistent_resp_rate, persistent_t_ins, persistent_t_exp, persistent_ie_ratio, persistent_last_updated
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    persistent_last_updated = now_str
    
    if max_f is not None: persistent_max_flow = float(max_f)
    if min_f is not None: persistent_min_flow = float(min_f)
    if rate is not None: persistent_resp_rate = float(rate)
    if t_in is not None: persistent_t_ins = float(t_in)
    if t_ex is not None: persistent_t_exp = float(t_ex)
    if ie is not None: persistent_ie_ratio = str(ie)
    
    config_data["profiles"][active_profile_name] = {
        "max_flow": persistent_max_flow,
        "min_flow": persistent_min_flow,
        "resp_rate": persistent_resp_rate,
        "t_ins": persistent_t_ins,
        "t_exp": persistent_t_exp,
        "ie_ratio": persistent_ie_ratio,
        "last_updated": persistent_last_updated
    }
    save_config()
    update_plot_header_labels()

def set_active_profile(name):
    global active_profile_name, persistent_max_flow, persistent_min_flow, persistent_resp_rate, persistent_t_ins, persistent_t_exp, persistent_ie_ratio, persistent_last_updated
    if name in config_data["profiles"]:
        active_profile_name = name
        config_data["active_profile"] = name
        prof = config_data["profiles"][name]
        persistent_max_flow = float(prof.get("max_flow", 100.0))
        persistent_min_flow = float(prof.get("min_flow", -100.0))
        persistent_resp_rate = float(prof.get("resp_rate", 0.0))
        persistent_t_ins = float(prof.get("t_ins", 0.0))
        persistent_t_exp = float(prof.get("t_exp", 0.0))
        persistent_ie_ratio = str(prof.get("ie_ratio", "1:2.0"))
        persistent_last_updated = str(prof.get("last_updated", "Nunca"))
        save_config()
        update_plot_header_labels()
        log(f"Perfil de usuário alterado para: '{name}'")

def create_new_profile(name):
    clean_name = name.strip()
    if not clean_name: return
    if clean_name not in config_data["profiles"]:
        config_data["profiles"][clean_name] = DEFAULT_PROFILE_DATA.copy()
    set_active_profile(clean_name)

def delete_profile(name):
    if name == "Padrão":
        messagebox.showwarning("Aviso", "O perfil 'Padrão' não pode ser excluído.")
        return
    if name in config_data["profiles"]:
        del config_data["profiles"][name]
        set_active_profile("Padrão")

def save_config():
    p = get_config_path()
    data = {
        "active_profile": active_profile_name,
        "profiles": config_data.get("profiles", {}),
        "com0com_installed": config_data.get("com0com_installed", False),
        "conn_mode": conn_mode_var.get() if 'conn_mode_var' in globals() else config_data.get("conn_mode"),
        "filter_mode": pressure_filter.mode if 'pressure_filter' in globals() else config_data.get("filter_mode"),
        "scale_multiplier": flow_multiplier if 'flow_multiplier' in globals() else config_data.get("scale_multiplier"),
        "scale_key": scale_opt_var.get() if 'scale_opt_var' in globals() else config_data.get("scale_key"),
        "game_port": port_var.get() if 'port_var' in globals() else config_data.get("game_port"),
        "oximeter_game_port": oxi_port_var.get() if 'oxi_port_var' in globals() else config_data.get("oximeter_game_port", "Somente monitor"),
        "output_mode": output_mode_var.get() if 'output_mode_var' in globals() else config_data.get("output_mode", "Pressão relativa (Pa)"),
        "device_port": device_port_var.get() if 'device_port_var' in globals() else config_data.get("device_port")
    }
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar config.json: {e}")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# Tratamento de chamada auxiliar de desinstalação com privilégios elevados
if "--uninstall-com0com" in sys.argv:
    try:
        base_p = os.path.join(sys._MEIPASS, "com0com") if hasattr(sys, '_MEIPASS') else os.path.join(os.path.abspath("."), "com0com")
        exe_path = os.path.join(base_p, "setupc.exe")
        subprocess.run([exe_path, "uninstall"], cwd=base_p, capture_output=True, creationflags=0x08000000)
        cfg = load_config()
        cfg["com0com_installed"] = False
        p = get_config_path()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except:
        pass
    sys.exit(0)

# Nao solicitar elevacao de administrador ao iniciar monitor de teste MPX5010DP.
com0com_is_installed = bool(config_data.get("com0com_installed", False))

def get_com0com_path():
    if hasattr(sys, '_MEIPASS'):
        base_p = os.path.join(sys._MEIPASS, "com0com")
    else:
        base_p = os.path.join(os.path.abspath("."), "com0com")
    return os.path.join(base_p, "setupc.exe")

def ensure_virtual_ports():
    if hasattr(sys, '_MEIPASS'):
        base_p = os.path.join(sys._MEIPASS, "com0com")
    else:
        base_p = os.path.join(os.path.abspath("."), "com0com")
    
    exe_path = os.path.join(base_p, "setupc.exe")
    if not os.path.exists(exe_path):
        return
    
    try:
        os.chdir(base_p)
        
        # 1. Verifica portas atuais
        result = subprocess.run([exe_path, "list"], capture_output=True, text=True, creationflags=0x08000000)
        
        if "CNCA" not in result.stdout:
            if is_admin():
                log("Instalando portas virtuais com0com...")
                subprocess.run([exe_path, "install", "-", "-"], capture_output=True, creationflags=0x08000000)
                
                # 2. Re-lista para saber qual número foi atribuído
                new_list = subprocess.run([exe_path, "list"], capture_output=True, text=True, creationflags=0x08000000)
                
                import re
                match = re.search(r"CNCB(\d+)", new_list.stdout)
                if match:
                    nova_porta = f"CNCB{match.group(1)}"
                    port_var.set(nova_porta) 
                    log(f"Portas configuradas: {nova_porta}")
                
                config_data["com0com_installed"] = True
                save_config()
                log("Portas com0com instaladas e registradas.")
            else:
                log("Aviso: Portas virtuais ausentes. Reabra como Administrador para instalá-las.")
        else:
            # Portas já existem no sistema
            import re
            match = re.search(r"CNCB(\d+)", result.stdout)
            if match:
                port_var.set(f"CNCB{match.group(1)}")
            
            if not config_data.get("com0com_installed", False):
                config_data["com0com_installed"] = True
                save_config()
            log("Portas virtuais prontas.")

    except Exception as e:
        log(f"Erro na automação de portas virtuais: {e}")

def uninstall_com0com():
    if messagebox.askyesno("Manutenção PITACO", "Deseja remover todas as portas virtuais do com0com?\n(Isso limpará os drivers do sistema)"):
        if not is_admin():
            try:
                script = os.path.abspath(sys.argv[0])
                if getattr(sys, 'frozen', False):
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "--uninstall-com0com", None, 1)
                else:
                    params = f'"{script}" --uninstall-com0com'
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
                
                config_data["com0com_installed"] = False
                save_config()
                messagebox.showinfo("Sucesso", "Drivers virtuais removidos com sucesso!")
                return
            except Exception as e:
                log(f"Falha ao solicitar privilégios: {e}")
                return

        exe_path = os.path.abspath(get_com0com_path())
        com_folder = os.path.dirname(exe_path)
        
        try:
            log("Iniciando remoção de portas virtuais...")
            process = subprocess.run(
                [exe_path, "uninstall"],
                cwd=com_folder,
                capture_output=True,
                creationflags=0x08000000
            )
            if process.returncode == 0:
                config_data["com0com_installed"] = False
                save_config()
                messagebox.showinfo("Sucesso", "Drivers virtuais removidos com sucesso!")
                log("Drivers com0com removidos.")
            else:
                messagebox.showwarning("Erro", "Falha ao desinstalar. Verifique se o programa está como Admin.")
        except Exception as e:
            log(f"Erro ao desinstalar: {e}")

# configurar
DEVICE_NAME = "PITACO V2.0"
SERVICE_UUID = "0f128d4d-3cf9-46de-bb31-ed159450d6cf"
CHARACTERISTIC_UUID = "3bcdff27-47fc-4a87-9684-7672c49d9266"
OTA_CONTROL_UUID = "3bcdff28-47fc-4a87-9684-7672c49d9266"
OTA_DATA_UUID = "3bcdff29-47fc-4a87-9684-7672c49d9266"
PPG_NOTIFY_UUID = "3bcdff2a-47fc-4a87-9684-7672c49d9266"
BAUDRATE = 115200

running = False
is_sampling = False
client = None
ser = None
ser_oxi = None
ser_device = None
oxi_sampling = False
last_oxi_sent = 0.0
ble_ppg_lines = BleJsonlBuffer()
ppg_monitor = PpgMonitor(max_points=300)
ble_loop = None
ble_loop_thread = None

last_value = 0.0
target_value = 0.0
last_update_time = time.time()
update_interval = 0.050 # 50ms

# Constantes para o cálculo de fluxo (Modelo Físico de Placa de Orifício / Bernoulli)
PITACO_RADIUS = 0.018                      # Raio do tubo principal (m) = 18mm
PITACO_ORIFICE_RADIUS = PITACO_RADIUS / 2.0 # Raio do orifício de restrição (m) = 9mm
AIR_DENSITY = 1.204                         # Densidade do ar a 20°C (kg/m³)
DISCHARGE_COEF = 0.62                      # Coeficiente de descarga do orifício padrão (Cd)

# Área da seção do orifício (m²)
ORIFICE_AREA = 3.1415926535 * (PITACO_ORIFICE_RADIUS ** 2)

# Fator base físico: Q = Cd * A * sqrt(2 * ΔP / ρ) convertido para L/min (x 60.000)
BASE_ORIFICE_FACTOR = DISCHARGE_COEF * ORIFICE_AREA * math.sqrt(2.0 / AIR_DENSITY) * 60000.0

MAX_POINTS = 100
plot_data_pressure = deque([0.0]*MAX_POINTS, maxlen=MAX_POINTS)
plot_data_flow = deque([0.0]*MAX_POINTS, maxlen=MAX_POINTS)
is_plotting = False
is_ppg_plotting = False

flow_multiplier = 5.0

# Firmware MPX5010DP faz ADC -> Volts -> Pa. NAO recalcular a tensao aqui.
# Fluxo L/min abaixo e estimado por modelo de orificio, NAO validado.
def parse_pressure_pa(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Leitura de pressao nao finita")
    return value

def output_for_unity(pressure_pa, estimated_flow):
    selected = output_mode_var.get() if 'output_mode_var' in globals() else "Pressão relativa (Pa)"
    return pressure_pa if selected == "Pressão relativa (Pa)" else estimated_flow

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

def get_all_com_ports():
    ports = set()
    for port in serial.tools.list_ports.comports():
        ports.add(port.device)
    try:
        pythoncom.CoInitialize()
        w = wmi.WMI()
        for sp in w.query("SELECT * FROM Win32_SerialPort"):
            if sp.DeviceID and sp.DeviceID not in ports:
                ports.add(sp.DeviceID)
    except Exception as e:
        print(f"WMI error: {e}")
    finally:
        pythoncom.CoUninitialize()
    return sorted(list(ports))

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

pressure_filter = PressureFilter("Moderado")

# --- SETUP DA GUI PRINCIPAL ---
ctk.set_appearance_mode("dark")

def get_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

icon_path = get_path("icon.ico")

root = ctk.CTk()
root.title("PITACO Bridge - MPX5010DP (TESTE)")
root.geometry("370x520")

# ícone
if os.path.exists(icon_path):
    root.iconbitmap(icon_path)
    root.after(200, lambda: root.wm_iconphoto(True, ImageTk.PhotoImage(Image.open(icon_path))))

# Ribbon Bar Superior (CustomTkinter Dark Theme)
ribbon_bar_frame = ctk.CTkFrame(root, fg_color="#1f1f1f", corner_radius=6)
ribbon_bar_frame.pack(pady=(10, 2), padx=15, fill="x")

# 1. Filtro OptionMenu
ctk.CTkLabel(ribbon_bar_frame, text="Filtro:", text_color="#aaaaaa", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(8, 2))
filter_opt_var = ctk.StringVar(value=config_data.get("filter_mode", "Moderado"))

def on_filter_change(choice):
    set_filter_mode(choice)
    save_config()

filter_menu = ctk.CTkOptionMenu(
    ribbon_bar_frame,
    values=["Moderado", "Agressivo", "Suave", "Desativado"],
    variable=filter_opt_var,
    command=on_filter_change,
    width=95,
    height=24,
    fg_color="#2b2b2b",
    button_color="#3a3a3a",
    button_hover_color="#4a4a4a"
)
filter_menu.pack(side="left", padx=(0, 6), pady=4)

# 2. Escala OptionMenu
ctk.CTkLabel(ribbon_bar_frame, text="Escala:", text_color="#aaaaaa", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(4, 2))
scale_opt_var = ctk.StringVar(value=config_data.get("scale_key", "5.0x"))
scale_map = {
    "1.0x": (1.0, "1.0x (Bruto)"),
    "2.0x": (2.0, "2.0x"),
    "5.0x": (5.0, "5.0x (~100L) (Padrão)"),
    "10.0x": (10.0, "10.0x (~200L)"),
    "15.0x": (15.0, "15.0x (~300L)")
}

def on_scale_change(choice):
    if choice in scale_map:
        val, name = scale_map[choice]
        set_flow_multiplier(val, name)
        save_config()

scale_menu = ctk.CTkOptionMenu(
    ribbon_bar_frame,
    values=["1.0x", "2.0x", "5.0x", "10.0x", "15.0x"],
    variable=scale_opt_var,
    command=on_scale_change,
    width=75,
    height=24,
    fg_color="#2b2b2b",
    button_color="#3a3a3a",
    button_hover_color="#4a4a4a"
)
scale_menu.pack(side="left", padx=(0, 6), pady=4)

# 3. Botão Discreto de Engrenagem (Configurações e Manutenção)
gear_btn = ctk.CTkButton(
    ribbon_bar_frame,
    text="⚙",
    width=28,
    height=24,
    fg_color="#2b2b2b",
    hover_color="#3a3a3a",
    font=("Segoe UI", 13),
    command=lambda: open_settings_window()
)
gear_btn.pack(side="right", padx=(0, 6), pady=4)

# Seletor de Modo de Conexão (BLE vs USB)
conn_mode_var = ctk.StringVar(value=config_data.get("conn_mode", "Cabo USB"))

mode_frame = ctk.CTkFrame(root, fg_color="transparent")
mode_frame.pack(pady=(5, 0), padx=15, fill="x")

def on_conn_mode_change(value):
    if value == "Cabo USB":
        device_port_frame.pack(pady=(5, 5), padx=15, fill="x", before=port_frame)
    else:
        device_port_frame.pack_forget()
    save_config()

conn_mode_segmented = ctk.CTkSegmentedButton(
    mode_frame,
    values=["Bluetooth", "Cabo USB"],
    variable=conn_mode_var,
    command=on_conn_mode_change
)
conn_mode_segmented.pack(fill="x")

# Modo de saida compatível com firmware: Pa relativos por padrao.
output_frame = ctk.CTkFrame(root, fg_color="transparent")
output_frame.pack(pady=(4, 0), padx=15, fill="x")
ctk.CTkLabel(output_frame, text="Saída ao jogo:", anchor="w").pack(side="left", padx=(2, 6))
output_mode_var = ctk.StringVar(value=config_data.get("output_mode", "Pressão relativa (Pa)"))
output_menu = ctk.CTkOptionMenu(
    output_frame, variable=output_mode_var,
    values=["Pressão relativa (Pa)", "Fluxo estimado (L/min)"],
    command=lambda _choice: save_config(), width=185
)
output_menu.pack(side="right")

# Frame da Porta Física do ESP32 (apenas para Modo USB)
device_port_frame = ctk.CTkFrame(root, fg_color="transparent")

# Espaçador à esquerda para alinhar com o botão ↻ da linha de baixo
ctk.CTkLabel(device_port_frame, text="", width=28).pack(side="left", padx=(0, 5))
ctk.CTkLabel(device_port_frame, text="Porta ESP32 (USB):", anchor="w").pack(side="left")

device_port_var = ctk.StringVar(value=config_data.get("device_port", ""))
device_port_combo = ctk.CTkComboBox(
    device_port_frame,
    variable=device_port_var,
    values=[],
    width=125,
    command=lambda e: save_config()
)
device_port_combo.pack(side="right")

# Frame da Porta Virtual do Jogo
port_frame = ctk.CTkFrame(root, fg_color="transparent")
port_frame.pack(pady=(5, 5), padx=15, fill="x")

def refresh_ports():
    refresh_btn.configure(state="disabled")
    def worker():
        ports = get_all_com_ports()
        port_combo.configure(values=["Somente monitor"] + ports)
        device_port_combo.configure(values=ports)
        oxi_port_combo.configure(values=["Somente monitor"] + ports)
        saved_game = config_data.get("game_port", "Somente monitor")
        saved_dev = config_data.get("device_port", "")
        saved_oxi = config_data.get("oximeter_game_port", "Somente monitor")
        oxi_port_var.set(saved_oxi if saved_oxi in ports else "Somente monitor")
        # Nunca abrir a COM fisica tambem como COM virtual do jogo.
        port_var.set(saved_game if saved_game in ports else "Somente monitor")
        if ports:
            device_port_var.set(saved_dev if saved_dev in ports else ports[0])
        refresh_btn.configure(state="normal")
        log(f"Portas COM disponíveis:\n{ports}\n")
    threading.Thread(target=worker, daemon=True).start()

# Botão de varredura ↻ à esquerda
refresh_btn = ctk.CTkButton(port_frame, text="↻", width=28, height=26, command=refresh_ports)
refresh_btn.pack(side="left", padx=(0, 5))

ctk.CTkLabel(port_frame, text="Porta Jogo (Virtual):", anchor="w").pack(side="left")

port_var = ctk.StringVar(value=config_data.get("game_port", "Somente monitor"))
port_combo = ctk.CTkComboBox(
    port_frame,
    variable=port_var,
    values=[],
    width=125,
    command=lambda e: save_config()
)
port_combo.pack(side="right")

# Segunda porta virtual, opcional: Unity SerialControllerOximetro (echox).
oxi_frame = ctk.CTkFrame(root, fg_color="transparent")
oxi_frame.pack(pady=(2, 5), padx=15, fill="x")
ctk.CTkLabel(oxi_frame, text="Porta Oxímetro (Virtual):", anchor="w").pack(side="left")
oxi_port_var = ctk.StringVar(value=config_data.get("oximeter_game_port", "Somente monitor"))
oxi_port_combo = ctk.CTkComboBox(
    oxi_frame, variable=oxi_port_var, values=["Somente monitor"], width=125,
    command=lambda _choice: save_config()
)
oxi_port_combo.pack(side="right")

# Exibe a porta física se o modo salvo for Cabo USB
if conn_mode_var.get() == "Cabo USB":
    root.after(100, lambda: device_port_frame.pack(pady=(5, 5), padx=15, fill="x", before=port_frame))

# tentar instalar as portas com0com se não estiverem
# Nao instalar o driver com0com automaticamente. Modo monitor nao precisa dele.
# root.after(500, ensure_virtual_ports)

# Botao Principal Start/Stop
def toggle_bridge():
    if running:
        stop_bridge()
    else:
        start_bridge()

bridge_btn = ctk.CTkButton(root, text="Conectar", fg_color="#28a745", hover_color="#218838", height=40, command=toggle_bridge)
bridge_btn.pack(pady=10, padx=15, fill="x")

# Status e Ferramentas
info_frame = ctk.CTkFrame(root, fg_color="transparent")
info_frame.pack(pady=5, padx=15, fill="x")

status_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
status_frame.pack(side="left")

def create_status_indicator(master, text):
    frame = ctk.CTkFrame(master, fg_color="transparent")
    label = ctk.CTkLabel(frame, text=text, width=45, anchor="e")
    indicator = ctk.CTkLabel(frame, text="", width=12, height=12, corner_radius=6, fg_color="red")
    label.pack(side="left")
    indicator.pack(side="left", padx=5)
    frame.pack(anchor="w")
    return indicator

status_serial = create_status_indicator(status_frame, "Serial:")
status_ble = create_status_indicator(status_frame, "BLE:")

def set_indicator(indicator, on):
    indicator.configure(fg_color="green" if on else "red")

tools_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
tools_frame.pack(side="right")

def send_ble_command(cmd):
    global client, ble_loop, is_sampling

    cmd_lower = cmd.lower()
    if cmd_lower == 'r':
        is_sampling = True
        pressure_filter.reset()
    elif cmd_lower in ['f', 'e']:
        is_sampling = False
    elif cmd_lower == 'c':
        pressure_filter.reset()

    if conn_mode_var.get() == "Cabo USB" and ser_device and ser_device.is_open:
        try:
            ser_device.write(cmd.encode('ascii'))
            log(f"[USB] Comando '{cmd}' enviado.")
        except Exception as exc:
            log(f"[USB] Erro: {exc}")
    elif client and client.is_connected and ble_loop:
        try:
            asyncio.run_coroutine_threadsafe(
                client.write_gatt_char(CHARACTERISTIC_UUID, cmd.encode('ascii'), response=True),
                ble_loop)
            log(f"[BLE] Comando '{cmd}' enviado.")
        except Exception as exc:
            log(f"[BLE] Erro: {exc}")

def open_graph():
    """Abre exclusivamente o painel respiratorio original."""
    global is_plotting
    is_plotting = True
    plot_window.deiconify()
    graph_btn.configure(state="disabled")
    send_ble_command('r')


def close_graph():
    """Fechar pneumo nao interrompe monitor PPG se ele ainda estiver aberto."""
    global is_plotting
    is_plotting = False
    plot_window.withdraw()
    graph_btn.configure(state="normal")
    if not is_ppg_plotting:
        send_ble_command('f')


def open_ppg_graph():
    """Abre monitor cardiaco separado, compartilhando a coleta existente."""
    global is_ppg_plotting
    is_ppg_plotting = True
    ppg_window.deiconify()
    ppg_graph_btn.configure(state="disabled")
    send_ble_command('r')


def close_ppg_graph():
    """Fechar PPG nao interrompe pneumo se o outro painel estiver aberto."""
    global is_ppg_plotting
    is_ppg_plotting = False
    ppg_window.withdraw()
    ppg_graph_btn.configure(state="normal")
    if not is_plotting:
        send_ble_command('f')


graph_btn = ctk.CTkButton(tools_frame, text="Gráfico Pneumo", width=155,
                          state="disabled", command=open_graph)
graph_btn.pack(pady=2)

ppg_graph_btn = ctk.CTkButton(tools_frame, text="Monitor Cardíaco / SpO₂",
                              width=155, state="disabled", command=open_ppg_graph)
ppg_graph_btn.pack(pady=2)

calib_btn = ctk.CTkButton(tools_frame, text="Calibrar Sensor", width=100, state="disabled", command=lambda: send_ble_command('c'))
calib_btn.pack(pady=2)

# A GUI aguarda confirmacao do firmware em duas fases:
# 1. zero_start ate 3 s apos enviar z; 2. zero_done ate 14 s apos o ACK.
# O clique nao e uma confirmacao do dispositivo.
zero_active = False
zero_waiting_ack = False
zero_deadline = 0.0

def zero_status(message):
    global zero_active, zero_waiting_ack, zero_deadline
    if message == "zero_start":
        zero_waiting_ack = False
        zero_active = True
        zero_deadline = time.monotonic() + 14.0
        zero_btn.configure(text="Zerando 10s", state="disabled")
        log("[ZERO] Confirmado pelo ESP32: coleta de 10 s iniciada. Mantenha em repouso.")
    elif message.startswith("zero_done:"):
        zero_waiting_ack = False
        zero_active = False
        zero_deadline = 0.0
        zero_btn.configure(text="Zerar (10 s)", state="normal")
        pressure_filter.reset()
        log("[ZERO] Concluido no ESP32. Novo offset (Pa): " + message.partition(":")[2])
    elif message.startswith("zero_error"):
        zero_waiting_ack = False
        zero_active = False
        zero_deadline = 0.0
        zero_btn.configure(text="Zerar (10 s)", state="normal")
        log("[ZERO] Firmware reportou falha: " + message + ". Referencia anterior preservada.")
    elif message == "zero_cancelled":
        zero_waiting_ack = False
        zero_active = False
        zero_deadline = 0.0
        zero_btn.configure(text="Zerar (10 s)", state="normal")
        log("[ZERO] Interrompido pelo comando de identificacao e (Unity).")

def start_zero():
    global zero_active, zero_waiting_ack, zero_deadline
    if not running or zero_active or zero_waiting_ack:
        return
    connected_usb = (conn_mode_var.get() == "Cabo USB"
                     and ser_device is not None and ser_device.is_open)
    connected_ble = (conn_mode_var.get() == "Bluetooth"
                     and client is not None and client.is_connected)
    if not (connected_usb or connected_ble):
        log("[ZERO] Dispositivo nao conectado: comando z nao enviado.")
        return
    zero_waiting_ack = True
    zero_deadline = time.monotonic() + 3.0
    zero_btn.configure(state="disabled", text="Aguardando ESP32")
    log("[ZERO] Enviando comando z; aguardando confirmacao zero_start.")
    send_ble_command("z")

def zero_tick():
    global zero_active, zero_waiting_ack, zero_deadline
    if zero_waiting_ack and time.monotonic() >= zero_deadline:
        zero_waiting_ack = False
        zero_btn.configure(text="Zerar (10 s)", state="normal")
        log("[ZERO] Sem resposta zero_start. Verifique se o firmware com comando z foi gravado.")
    elif zero_active:
        remaining = zero_deadline - time.monotonic()
        if remaining <= 0:
            zero_active = False
            zero_btn.configure(text="Zerar (10 s)", state="normal")
            log("[ZERO] ESP32 iniciou a calibracao mas nao enviou zero_done/zero_error.")
            log("[ZERO] Confira cabos/porta e se Unity enviou e durante a calibracao.")
        else:
            # 14s inclui margem para entrega. Temporizador visual de 10s.
            zero_btn.configure(text=f"Zerando {min(10, max(0, int(remaining - 4)))}s")
    root.after(250, zero_tick)

zero_btn = ctk.CTkButton(tools_frame, text="Zerar (10 s)", width=100, state="disabled", command=start_zero)
zero_btn.pack(pady=2)
root.after(250, zero_tick)

# Logs
log_box = ctk.CTkTextbox(root, height=120)

def clear_log():
    log_box.configure(state="normal") # Garante que está editável para limpar
    log_box.delete("1.0", "end")

def set_filter_mode(mode):
    pressure_filter.set_mode(mode)
    log(f"Filtro de picos alterado para: {mode}")

def set_flow_multiplier(val, name):
    global flow_multiplier
    flow_multiplier = val
    log(f"Escala de fluxo alterada para: {val}x ({name})")

OTA_UPGRADE_URL = "https://leoflt.com/s/pitaco2-0-firmware-upgrade"

def flash_firmware_usb(file_path=None):
    port = device_port_var.get() or port_var.get()
    if not port:
        messagebox.showwarning("Aviso", "Selecione uma porta COM para a gravação via cabo USB.")
        return

    if not file_path:
        file_path = filedialog.askopenfilename(
            title="Selecione o arquivo de firmware (.bin)",
            filetypes=[("Binário ESP32", "*.bin"), ("Todos os arquivos", "*.*")]
        )
        if not file_path:
            return

    if messagebox.askyesno("Confirmar Gravação USB", f"Deseja gravar o firmware:\n{os.path.basename(file_path)}\nna porta {port}?"):
        def worker():
            global ser, ser_device, running
            log(f"[USB Flash]: Iniciando gravação do firmware {os.path.basename(file_path)} em {port}...")
            was_open_ser = False
            was_open_dev = False
            
            if ser and ser.is_open:
                was_open_ser = True
                try:
                    ser.close()
                except:
                    pass

            if ser_device and ser_device.is_open:
                was_open_dev = True
                try:
                    ser_device.close()
                except:
                    pass

            clean_port = port.replace("\\\\.\\", "")
            try:
                cmd_args = [
                    '--chip', 'auto',
                    '--port', clean_port,
                    '--baud', '921600',
                    'write_flash', '-z', '0x10000', file_path
                ]
                esptool.main(cmd_args)
                log("[USB Flash]: Gravação USB concluída com SUCESSO!")
                messagebox.showinfo("Sucesso", "Firmware gravado com sucesso via USB!")
            except Exception as e:
                log(f"[USB Flash]: Erro durante a gravação: {e}")
                messagebox.showerror("Erro de Gravação", f"Falha na gravação USB:\n{e}")
            finally:
                if was_open_ser and running:
                    try:
                        ser.open()
                    except:
                        pass
                if was_open_dev and running:
                    try:
                        ser_device.open()
                    except:
                        pass

        threading.Thread(target=worker, daemon=True).start()

def send_ble_ota_bytes(bin_data, display_name="firmware.bin"):
    global client, ble_loop
    if not (client and client.is_connected and ble_loop):
        messagebox.showwarning("Aviso", "Conecte o PITACO via BLE antes de iniciar o OTA sem fio.")
        return

    async def ota_worker():
        try:
            total_bytes = len(bin_data)
            log(f"[BLE OTA]: Iniciando transferência de {display_name} ({total_bytes} bytes)...")

            start_payload = bytes([0x01]) + struct.pack("<I", total_bytes)
            await client.write_gatt_char(OTA_CONTROL_UUID, start_payload, response=True)
            await asyncio.sleep(0.5)

            chunk_size = 512
            sent_bytes = 0
            last_log_pct = -10

            for i in range(0, total_bytes, chunk_size):
                chunk = bin_data[i:i+chunk_size]
                await client.write_gatt_char(OTA_DATA_UUID, chunk, response=False)
                sent_bytes += len(chunk)
                pct = int((sent_bytes / total_bytes) * 100)
                if pct >= last_log_pct + 10 or sent_bytes == total_bytes:
                    last_log_pct = pct
                    log(f"[BLE OTA]: Progresso {pct}% ({sent_bytes}/{total_bytes} bytes)")
                await asyncio.sleep(0.01)

            end_payload = bytes([0x02])
            await client.write_gatt_char(OTA_CONTROL_UUID, end_payload, response=True)
            log("[BLE OTA]: Transferência concluída com SUCESSO! O PITACO está reiniciando...")
            messagebox.showinfo("Sucesso", "Firmware atualizado via BLE OTA! Dispositivo reiniciando...")

        except Exception as e:
            log(f"[BLE OTA]: Erro na atualização OTA: {e}")
            messagebox.showerror("Erro OTA", f"Falha na atualização sem fio:\n{e}")

    asyncio.run_coroutine_threadsafe(ota_worker(), ble_loop)

def flash_firmware_ble_ota():
    file_path = filedialog.askopenfilename(
        title="Selecione o arquivo de firmware (.bin)",
        filetypes=[("Binário ESP32", "*.bin"), ("Todos os arquivos", "*.*")]
    )
    if not file_path:
        return

    if messagebox.askyesno("Confirmar OTA Sem Fio", f"Deseja enviar o firmware sem fio (BLE):\n{os.path.basename(file_path)}?"):
        try:
            with open(file_path, "rb") as f:
                bin_data = f.read()
            send_ble_ota_bytes(bin_data, os.path.basename(file_path))
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao ler arquivo: {e}")

def flash_firmware_online_ota():
    def worker():
        log("[Atualização Online]: Verificando e baixando firmware mais recente...")
        try:
            req = urllib.request.Request(
                OTA_UPGRADE_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PITACO-Bridge/2.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                bin_data = response.read()

            if not bin_data or len(bin_data) < 1000:
                raise Exception("Arquivo de atualização recebido é inválido ou está vazio.")

            log(f"[Atualização Online]: Firmware baixado com sucesso ({len(bin_data)} bytes)!")

            mode = conn_mode_var.get()
            if mode == "Bluetooth":
                if not (client and client.is_connected):
                    messagebox.showinfo("Firmware Baixado", "Download concluído com sucesso!\n\nConecte-se ao PITACO via Bluetooth e clique novamente para aplicar a atualização.")
                    return

                if messagebox.askyesno("Confirmar Atualização", "Firmware baixado com sucesso!\n\nDeseja iniciar a atualização sem fio (BLE OTA) agora?"):
                    send_ble_ota_bytes(bin_data, "PITACO_Online_OTA.bin")
            else:
                # Modo Cabo USB
                port = device_port_var.get() or port_var.get()
                if not port:
                    messagebox.showinfo("Firmware Baixado", "Download concluído com sucesso!\n\nSelecione a porta USB do ESP32 para realizar a gravação.")
                    return

                if messagebox.askyesno("Confirmar Gravação USB", f"Firmware baixado com sucesso!\n\nDeseja gravar via USB na porta {port}?"):
                    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                        tmp.write(bin_data)
                        tmp_path = tmp.name

                    try:
                        flash_firmware_usb(file_path=tmp_path)
                    finally:
                        try:
                            os.remove(tmp_path)
                        except:
                            pass

        except Exception as e:
            log(f"[Atualização Online]: Falha ao obter firmware: {e}")
            messagebox.showerror("Atualização Online", "Não foi possível baixar o firmware no momento.\nVerifique sua conexão com a internet ou tente mais tarde.")

    threading.Thread(target=worker, daemon=True).start()

def open_settings_window():
    settings_win = ctk.CTkToplevel(root)
    settings_win.title("Configurações e Perfis")
    settings_win.geometry("360x430")
    settings_win.resizable(False, False)
    settings_win.attributes("-topmost", True)

    main_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
    main_frame.pack(fill="both", expand=True, padx=15, pady=15)

    # 1. Seção de Perfis de Usuário
    ctk.CTkLabel(main_frame, text="👤 Perfil de Usuário / Paciente", font=("Segoe UI", 13, "bold"), text_color="#ffffff").pack(anchor="w", pady=(0, 4))
    
    prof_row = ctk.CTkFrame(main_frame, fg_color="transparent")
    prof_row.pack(fill="x", pady=(0, 6))

    prof_names = list(config_data.get("profiles", {}).keys())
    prof_var = ctk.StringVar(value=active_profile_name)

    def on_prof_selected(name):
        set_active_profile(name)

    prof_combo = ctk.CTkComboBox(
        prof_row,
        variable=prof_var,
        values=prof_names,
        width=170,
        command=on_prof_selected
    )
    prof_combo.pack(side="left", padx=(0, 4))

    def on_add_profile():
        dialog = ctk.CTkInputDialog(text="Digite o nome do novo paciente/perfil:", title="Novo Perfil")
        new_name = dialog.get_input()
        if new_name and new_name.strip():
            clean_name = new_name.strip()
            create_new_profile(clean_name)
            updated_names = list(config_data["profiles"].keys())
            prof_combo.configure(values=updated_names)
            prof_var.set(clean_name)

    btn_add_prof = ctk.CTkButton(
        prof_row,
        text="+ Novo",
        width=65,
        height=28,
        fg_color="#1f538d",
        hover_color="#14375e",
        command=on_add_profile
    )
    btn_add_prof.pack(side="left", padx=2)

    def on_del_profile():
        cur = prof_var.get()
        if cur == "Padrão":
            messagebox.showwarning("Aviso", "O perfil 'Padrão' não pode ser excluído.")
            return
        if messagebox.askyesno("Excluir Perfil", f"Deseja realmente excluir o perfil '{cur}'?"):
            delete_profile(cur)
            updated_names = list(config_data["profiles"].keys())
            prof_combo.configure(values=updated_names)
            prof_var.set("Padrão")

    btn_del_prof = ctk.CTkButton(
        prof_row,
        text="🗑",
        width=30,
        height=28,
        fg_color="#444444",
        hover_color="#631414",
        command=on_del_profile
    )
    btn_del_prof.pack(side="left", padx=2)

    sep_prof = ctk.CTkFrame(main_frame, height=1, fg_color="#3a3a3a")
    sep_prof.pack(fill="x", pady=6)

    # 2. Seção de Manutenção e Firmware
    ctk.CTkLabel(main_frame, text="⚙ Manutenção e Firmware", font=("Segoe UI", 13, "bold"), text_color="#ffffff").pack(anchor="w", pady=(0, 6))

    btn_online = ctk.CTkButton(
        main_frame,
        text="☁  Atualização Online (OTA Automático)",
        fg_color="#1f538d",
        hover_color="#14375e",
        height=32,
        command=lambda: (settings_win.destroy(), flash_firmware_online_ota())
    )
    btn_online.pack(fill="x", pady=3)

    btn_usb = ctk.CTkButton(
        main_frame,
        text="📁  Gravar Arquivo Local (.bin) via USB",
        fg_color="#2b2b2b",
        hover_color="#3a3a3a",
        height=32,
        command=lambda: (settings_win.destroy(), flash_firmware_usb())
    )
    btn_usb.pack(fill="x", pady=3)

    btn_ble = ctk.CTkButton(
        main_frame,
        text="📡  Gravar Arquivo Local (.bin) via BLE OTA",
        fg_color="#2b2b2b",
        hover_color="#3a3a3a",
        height=32,
        command=lambda: (settings_win.destroy(), flash_firmware_ble_ota())
    )
    btn_ble.pack(fill="x", pady=3)

    sep = ctk.CTkFrame(main_frame, height=1, fg_color="#3a3a3a")
    sep.pack(fill="x", pady=6)

    btn_ports = ctk.CTkButton(
        main_frame,
        text="🗑  Desinstalar Portas Virtuais (com0com)",
        fg_color="#631414",
        hover_color="#4a0f0f",
        height=28,
        command=lambda: (settings_win.destroy(), uninstall_com0com())
    )
    btn_ports.pack(fill="x", pady=2)

def show_context_menu(event):
    context_menu = Menu(root, tearoff=0)
    context_menu.add_command(label="Limpar janela de log", command=clear_log)
    context_menu.add_separator()
    context_menu.add_command(label="Desinstalar Portas Virtuais", command=uninstall_com0com)
    context_menu.post(event.x_root, event.y_root)

# botão direito do mouse (Button-3) 
log_box.bind("<Button-3>", show_context_menu)

log_box.pack(padx=15, pady=(10, 15), fill="both", expand=True)

def log(msg):
    log_box.insert(ctk.END, msg + "\n")
    log_box.see(ctk.END)

# --- POPUP DO GRAFICO ---
plot_window = ctk.CTkToplevel(root)
plot_window.title("PITACO 2.4 - Pneumógrafo")
plot_window.geometry("820x560")
plot_window.protocol("WM_DELETE_WINDOW", close_graph)
plot_window.withdraw() 

popup_header_frame = ctk.CTkFrame(plot_window, fg_color="#1f1f1f", corner_radius=6)
popup_header_frame.pack(fill="x", padx=15, pady=(10, 5))

# Linha 1 do Header
header_top_row = ctk.CTkFrame(popup_header_frame, fg_color="transparent")
header_top_row.pack(fill="x", padx=8, pady=(6, 2))

profile_badge_label = ctk.CTkLabel(header_top_row, text=f"👤 Perfil: {active_profile_name}", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0")
profile_badge_label.pack(side="left", padx=(0, 10))

current_val_label = ctk.CTkLabel(header_top_row, text="Fluxo: 0.00 L/min", font=("Segoe UI", 13, "bold"), text_color="#ffffff")
current_val_label.pack(side="left", padx=(0, 10))

max_val_label = ctk.CTkLabel(header_top_row, text=f"Máx (Exp): +{persistent_max_flow:.2f} L/min", font=("Segoe UI", 12, "bold"), text_color="#28a745")
max_val_label.pack(side="left", padx=(0, 10))

min_val_label = ctk.CTkLabel(header_top_row, text=f"Mín (Insp): {persistent_min_flow:.2f} L/min", font=("Segoe UI", 12, "bold"), text_color="#17a2b8")
min_val_label.pack(side="left", padx=(0, 10))

# Linha 2 do Header (Métricas em formato de texto)
header_bottom_row = ctk.CTkFrame(popup_header_frame, fg_color="transparent")
header_bottom_row.pack(fill="x", padx=8, pady=(2, 6))

rate_val_label = ctk.CTkLabel(header_bottom_row, text=f"Taxa: {persistent_resp_rate:.0f} rpm" if persistent_resp_rate > 0 else "Taxa: -- rpm", font=("Segoe UI", 11, "bold"), text_color="#ffc107")
rate_val_label.pack(side="left", padx=(0, 15))

init_timing_text = f"Ins: {persistent_t_ins:.1f}s | Exp: {persistent_t_exp:.1f}s | I:E {persistent_ie_ratio}" if (persistent_t_ins > 0 and persistent_t_exp > 0) else "Tempos Ins/Exp: --"
timing_val_label = ctk.CTkLabel(header_bottom_row, text=init_timing_text, font=("Segoe UI", 11), text_color="#e0e0e0")
timing_val_label.pack(side="left", padx=(0, 10))

def open_info_window():
    info_win = ctk.CTkToplevel(plot_window)
    info_win.title("Relatório experimental - sem validação clínica")
    info_win.geometry("450x460")
    info_win.resizable(False, False)
    info_win.attributes("-topmost", True)

    main_f = ctk.CTkFrame(info_win, fg_color="transparent")
    main_f.pack(fill="both", expand=True, padx=20, pady=15)

    title_lbl = ctk.CTkLabel(main_f, text="📋 Relatório Respiratório Experimental", font=("Segoe UI", 15, "bold"), text_color="#ffffff")
    title_lbl.pack(anchor="w", pady=(0, 2))

    sub_lbl = ctk.CTkLabel(main_f, text=f"Paciente / Perfil: {active_profile_name}  |  Última Aferição: {persistent_last_updated}", font=("Segoe UI", 11), text_color="#aaaaaa")
    sub_lbl.pack(anchor="w", pady=(0, 10))

    # Card 1: Picos de Fluxo
    c1 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
    c1.pack(fill="x", pady=4, padx=2)
    ctk.CTkLabel(c1, text="Picos de Fluxo Máximo e Mínimo", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
    ctk.CTkLabel(c1, text=f"• Pico Expiratório Máximo (PEF):  +{persistent_max_flow:.2f} L/min", font=("Segoe UI", 11), text_color="#28a745").pack(anchor="w", padx=12, pady=1)
    ctk.CTkLabel(c1, text=f"• Pico Inspiratório Mínimo (PIF):  {persistent_min_flow:.2f} L/min", font=("Segoe UI", 11), text_color="#17a2b8").pack(anchor="w", padx=12, pady=(1, 6))

    # Card 2: Taxa Respiratória
    c2 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
    c2.pack(fill="x", pady=4, padx=2)
    ctk.CTkLabel(c2, text="Taxa Respiratória (Freq. em Repouso)", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
    rate_str = f"{persistent_resp_rate:.0f} rpm (incursões/min)" if persistent_resp_rate > 0 else "Não aferida"
    ctk.CTkLabel(c2, text=f"• Taxa Medida (1 min):  {rate_str}", font=("Segoe UI", 11), text_color="#ffc107").pack(anchor="w", padx=12, pady=1)
    ctk.CTkLabel(c2, text="  ↳ Faixa de referência em repouso: 12 a 20 rpm", font=("Segoe UI", 10), text_color="#888888").pack(anchor="w", padx=12, pady=(1, 6))

    # Card 3: Cinética e Tempos de Ciclo
    c3 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
    c3.pack(fill="x", pady=4, padx=2)
    ctk.CTkLabel(c3, text="Cinética Respiratória (Tempos Ins / Exp)", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
    if persistent_t_ins > 0 and persistent_t_exp > 0:
        ctk.CTkLabel(c3, text=f"• Tempo Inspiratório Médio (T.ins):  {persistent_t_ins:.2f} s", font=("Segoe UI", 11), text_color="#ffffff").pack(anchor="w", padx=12, pady=1)
        ctk.CTkLabel(c3, text=f"• Tempo Expiratório Médio (T.exp):  {persistent_t_exp:.2f} s", font=("Segoe UI", 11), text_color="#ffffff").pack(anchor="w", padx=12, pady=1)
        ctk.CTkLabel(c3, text=f"• Relação I:E:  {persistent_ie_ratio}", font=("Segoe UI", 11, "bold"), text_color="#28a745").pack(anchor="w", padx=12, pady=1)
    else:
        ctk.CTkLabel(c3, text="• Tempos ainda não aferidos.", font=("Segoe UI", 11), text_color="#888888").pack(anchor="w", padx=12, pady=1)
    ctk.CTkLabel(c3, text="  ↳ Relação fisiológica de referência: 1:1.5 a 1:2.0", font=("Segoe UI", 10), text_color="#888888").pack(anchor="w", padx=12, pady=(1, 6))

    btn_close = ctk.CTkButton(main_f, text="Fechar", width=100, height=30, command=info_win.destroy)
    btn_close.pack(pady=(10, 0))

def start_peak_calibration():
    if not running:
        messagebox.showwarning("Aviso", "Conecte o PITACO (via Bluetooth ou Cabo USB) antes de aferir os picos de fluxo.")
        return

    # Garante envio do comando 'r' para ativar amostragem
    if conn_mode_var.get() == "Bluetooth":
        send_ble_command('r')
    else:
        if ser_device and ser_device.is_open:
            try:
                ser_device.write(b'r')
            except:
                pass

    calib_win = ctk.CTkToplevel(plot_window)
    calib_win.title("Aferição de Picos de Fluxo")
    calib_win.geometry("420x460")
    calib_win.resizable(False, False)
    calib_win.attributes("-topmost", True)

    main_f = ctk.CTkFrame(calib_win, fg_color="transparent")
    main_f.pack(fill="both", expand=True, padx=20, pady=15)

    title_lbl = ctk.CTkLabel(main_f, text="📊 Protocolo de Aferição de Picos", font=("Segoe UI", 14, "bold"), text_color="#ffffff")
    title_lbl.pack(pady=(0, 2))

    status_lbl = ctk.CTkLabel(main_f, text="Fase 1: Inspiração (1/3)", font=("Segoe UI", 15, "bold"), text_color="#3b8ed0")
    status_lbl.pack(pady=2)

    instruction_lbl = ctk.CTkLabel(main_f, text="Prepare-se para iniciar...", font=("Segoe UI", 12), text_color="#cccccc")
    instruction_lbl.pack(pady=2)

    timer_lbl = ctk.CTkLabel(main_f, text="3.0s", font=("Segoe UI", 24, "bold"), text_color="#ffc107")
    timer_lbl.pack(pady=4)

    results_frame = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
    results_frame.pack(fill="x", pady=4, padx=5)

    # Seção 1: Inspirações (Mínimo)
    ctk.CTkLabel(results_frame, text="Inspirações (Pico Inspiratório - Mínimo):", font=("Segoe UI", 11, "bold"), text_color="#17a2b8").pack(anchor="w", padx=10, pady=(6, 2))
    ins1_lbl = ctk.CTkLabel(results_frame, text="  1ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins1_lbl.pack(anchor="w", padx=10, pady=1)
    ins2_lbl = ctk.CTkLabel(results_frame, text="  2ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins2_lbl.pack(anchor="w", padx=10, pady=1)
    ins3_lbl = ctk.CTkLabel(results_frame, text="  3ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins3_lbl.pack(anchor="w", padx=10, pady=1)

    # Seção 2: Expirações (Máximo)
    ctk.CTkLabel(results_frame, text="Expirações (Pico Expiratório - Máximo):", font=("Segoe UI", 11, "bold"), text_color="#28a745").pack(anchor="w", padx=10, pady=(6, 2))
    exp1_lbl = ctk.CTkLabel(results_frame, text="  1ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp1_lbl.pack(anchor="w", padx=10, pady=1)
    exp2_lbl = ctk.CTkLabel(results_frame, text="  2ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp2_lbl.pack(anchor="w", padx=10, pady=1)
    exp3_lbl = ctk.CTkLabel(results_frame, text="  3ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp3_lbl.pack(anchor="w", padx=10, pady=(1, 6))

    cancel_flag = {"cancel": False}

    def on_close():
        cancel_flag["cancel"] = True
        calib_win.destroy()

    calib_win.protocol("WM_DELETE_WINDOW", on_close)

    action_btn = ctk.CTkButton(main_f, text="Cancelar", fg_color="#631414", hover_color="#4a0f0f", height=30, command=on_close)
    action_btn.pack(pady=(6, 0))

    def calib_worker():
        min_peaks = []
        max_peaks = []

        ins_labels = [ins1_lbl, ins2_lbl, ins3_lbl]
        exp_labels = [exp1_lbl, exp2_lbl, exp3_lbl]

        # --- FASE 1: 3x INSPIRAÇÕES ---
        for attempt in range(1, 4):
            if cancel_flag["cancel"]: return

            calib_win.after(0, lambda a=attempt: status_lbl.configure(text=f"Fase 1: Inspiração ({a}/3)", text_color="#17a2b8"))
            calib_win.after(0, lambda: instruction_lbl.configure(text="Prepare-se para puxar o ar..."))

            # Contagem de preparação (3s)
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                calib_win.after(0, lambda s=sec: timer_lbl.configure(text=f"{s}s", text_color="#ffc107"))
                time.sleep(1.0)

            if cancel_flag["cancel"]: return
            calib_win.after(0, lambda: instruction_lbl.configure(text="PUXE TODO O AR COM FORÇA MÁXIMA!"))
            calib_win.after(0, lambda: timer_lbl.configure(text_color="#17a2b8"))

            # Captura ativa (5s)
            start_time = time.time()
            attempt_samples = []

            while time.time() - start_time < 5.0:
                if cancel_flag["cancel"]: return
                rem = max(0.0, 5.0 - (time.time() - start_time))
                calib_win.after(0, lambda r=rem: timer_lbl.configure(text=f"{r:.1f}s"))

                if len(plot_data_flow) > 0:
                    attempt_samples.append(plot_data_flow[-1])

                time.sleep(0.05)

            p_min = min(attempt_samples) if attempt_samples else 0.0
            min_peaks.append(p_min)

            res_text = f"  {attempt}ª Inspiração: {p_min:.2f} L/min"
            lbl_w = ins_labels[attempt - 1]
            calib_win.after(0, lambda l=lbl_w, t=res_text: l.configure(text=t, text_color="#17a2b8"))

            # Intervalo de descanso (3s)
            calib_win.after(0, lambda: instruction_lbl.configure(text="Descanse um instante..."))
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                calib_win.after(0, lambda s=sec: timer_lbl.configure(text=f"Descanso: {s}s", text_color="#aaaaaa"))
                time.sleep(1.0)

        # --- FASE 2: 3x EXPIRAÇÕES ---
        for attempt in range(1, 4):
            if cancel_flag["cancel"]: return

            calib_win.after(0, lambda a=attempt: status_lbl.configure(text=f"Fase 2: Expiração ({a}/3)", text_color="#28a745"))
            calib_win.after(0, lambda: instruction_lbl.configure(text="Prepare-se para soprar o ar..."))

            # Contagem de preparação (3s)
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                calib_win.after(0, lambda s=sec: timer_lbl.configure(text=f"{s}s", text_color="#ffc107"))
                time.sleep(1.0)

            if cancel_flag["cancel"]: return
            calib_win.after(0, lambda: instruction_lbl.configure(text="SOPRE TODO O AR COM FORÇA MÁXIMA!"))
            calib_win.after(0, lambda: timer_lbl.configure(text_color="#28a745"))

            # Captura ativa (5s)
            start_time = time.time()
            attempt_samples = []

            while time.time() - start_time < 5.0:
                if cancel_flag["cancel"]: return
                rem = max(0.0, 5.0 - (time.time() - start_time))
                calib_win.after(0, lambda r=rem: timer_lbl.configure(text=f"{r:.1f}s"))

                if len(plot_data_flow) > 0:
                    attempt_samples.append(plot_data_flow[-1])

                time.sleep(0.05)

            p_max = max(attempt_samples) if attempt_samples else 0.0
            max_peaks.append(p_max)

            res_text = f"  {attempt}ª Expiração: +{p_max:.2f} L/min"
            lbl_w = exp_labels[attempt - 1]
            calib_win.after(0, lambda l=lbl_w, t=res_text: l.configure(text=t, text_color="#28a745"))

            # Intervalo de descanso entre expirações (se não for a última)
            if attempt < 3:
                calib_win.after(0, lambda: instruction_lbl.configure(text="Descanse um instante..."))
                for sec in range(3, 0, -1):
                    if cancel_flag["cancel"]: return
                    calib_win.after(0, lambda s=sec: timer_lbl.configure(text=f"Descanso: {s}s", text_color="#aaaaaa"))
                    time.sleep(1.0)

        if cancel_flag["cancel"]: return

        # Médias finais
        avg_min = round(sum(min_peaks) / 3.0, 2)
        avg_max = round(sum(max_peaks) / 3.0, 2)

        update_active_profile_metrics(max_f=avg_max, min_f=avg_min)

        calib_win.after(0, lambda: status_lbl.configure(text="Aferição Concluída!", text_color="#28a745"))
        calib_win.after(0, lambda: instruction_lbl.configure(text=f"Médias Salvas: Insp = {avg_min:.2f} | Exp = +{avg_max:.2f} L/min"))
        calib_win.after(0, lambda: timer_lbl.configure(text="100%", text_color="#28a745"))
        calib_win.after(0, lambda: action_btn.configure(text="Salvar e Fechar", fg_color="#28a745", hover_color="#218838", command=calib_win.destroy))

        log(f"[Aferição de Picos]: Concluída. Média Insp = {avg_min:.2f} L/min | Média Exp = +{avg_max:.2f} L/min.")

    threading.Thread(target=calib_worker, daemon=True).start()

def start_rate_calibration():
    if not running:
        messagebox.showwarning("Aviso", "Conecte o PITACO antes de aferir a taxa respiratória.")
        return

    if conn_mode_var.get() == "Bluetooth":
        send_ble_command('r')
    else:
        if ser_device and ser_device.is_open:
            try: ser_device.write(b'r')
            except: pass

    rate_win = ctk.CTkToplevel(plot_window)
    rate_win.title("Aferição de Taxa Respiratória (1 min)")
    rate_win.geometry("400x320")
    rate_win.resizable(False, False)
    rate_win.attributes("-topmost", True)

    main_f = ctk.CTkFrame(rate_win, fg_color="transparent")
    main_f.pack(fill="both", expand=True, padx=20, pady=15)

    ctk.CTkLabel(main_f, text="📊 Taxa Respiratória (1 Minuto)", font=("Segoe UI", 14, "bold"), text_color="#ffffff").pack(pady=(0, 2))
    status_lbl = ctk.CTkLabel(main_f, text="Respire normalmente em repouso...", font=("Segoe UI", 13), text_color="#3b8ed0")
    status_lbl.pack(pady=2)

    timer_lbl = ctk.CTkLabel(main_f, text="60.0s", font=("Segoe UI", 26, "bold"), text_color="#ffc107")
    timer_lbl.pack(pady=8)

    counter_lbl = ctk.CTkLabel(main_f, text="Ciclos Detectados: 0", font=("Segoe UI", 14, "bold"), text_color="#28a745")
    counter_lbl.pack(pady=4)

    cancel_flag = {"cancel": False}
    def on_close():
        cancel_flag["cancel"] = True
        rate_win.destroy()

    rate_win.protocol("WM_DELETE_WINDOW", on_close)
    action_btn = ctk.CTkButton(main_f, text="Cancelar", fg_color="#631414", hover_color="#4a0f0f", height=30, command=on_close)
    action_btn.pack(pady=(12, 0))

    def worker():
        cycles = 0
        state = "IDLE"
        start_time = time.time()
        duration = 60.0

        while time.time() - start_time < duration:
            if cancel_flag["cancel"]: return
            elapsed = time.time() - start_time
            rem = max(0.0, duration - elapsed)
            rate_win.after(0, lambda r=rem: timer_lbl.configure(text=f"{r:.1f}s"))

            if len(plot_data_flow) > 0:
                cur_flow = plot_data_flow[-1]
                if state == "IDLE":
                    if cur_flow > 3.0:
                        state = "EXP"
                    elif cur_flow < -3.0:
                        state = "INS"
                elif state == "EXP":
                    if cur_flow < -3.0:
                        state = "INS"
                elif state == "INS":
                    if cur_flow > 3.0:
                        cycles += 1
                        state = "EXP"
                        rate_win.after(0, lambda c=cycles: counter_lbl.configure(text=f"Ciclos Detectados: {c}"))

            time.sleep(0.03)

        if cancel_flag["cancel"]: return

        final_rpm = float(cycles)
        update_active_profile_metrics(rate=final_rpm)

        rate_win.after(0, lambda: status_lbl.configure(text="Aferição Concluída!", text_color="#28a745"))
        rate_win.after(0, lambda: timer_lbl.configure(text="100%", text_color="#28a745"))
        rate_win.after(0, lambda: counter_lbl.configure(text=f"Taxa Final: {final_rpm:.0f} rpm", text_color="#ffffff"))
        rate_win.after(0, lambda: action_btn.configure(text="Salvar e Fechar", fg_color="#28a745", hover_color="#218838", command=rate_win.destroy))
        log(f"[Taxa Respiratória]: Concluída. {final_rpm:.0f} rpm.")

    threading.Thread(target=worker, daemon=True).start()

def start_timing_calibration():
    if not running:
        messagebox.showwarning("Aviso", "Conecte o PITACO antes de aferir os tempos respiratórios.")
        return

    if conn_mode_var.get() == "Bluetooth":
        send_ble_command('r')
    else:
        if ser_device and ser_device.is_open:
            try: ser_device.write(b'r')
            except: pass

    timing_win = ctk.CTkToplevel(plot_window)
    timing_win.title("Aferição de Tempos de Ins / Exp")
    timing_win.geometry("420x460")
    timing_win.resizable(False, False)
    timing_win.attributes("-topmost", True)

    main_f = ctk.CTkFrame(timing_win, fg_color="transparent")
    main_f.pack(fill="both", expand=True, padx=20, pady=15)

    title_lbl = ctk.CTkLabel(main_f, text="📊 Protocolo de Tempos (Ins / Exp)", font=("Segoe UI", 14, "bold"), text_color="#ffffff")
    title_lbl.pack(pady=(0, 2))

    status_lbl = ctk.CTkLabel(main_f, text="Fase 1: Tempo Inspiratório (1/3)", font=("Segoe UI", 15, "bold"), text_color="#3b8ed0")
    status_lbl.pack(pady=2)

    instruction_lbl = ctk.CTkLabel(main_f, text="Prepare-se para iniciar...", font=("Segoe UI", 12), text_color="#cccccc")
    instruction_lbl.pack(pady=2)

    timer_lbl = ctk.CTkLabel(main_f, text="3.0s", font=("Segoe UI", 24, "bold"), text_color="#ffc107")
    timer_lbl.pack(pady=4)

    results_frame = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
    results_frame.pack(fill="x", pady=4, padx=5)

    # Seção 1: Inspirações
    ctk.CTkLabel(results_frame, text="Tempos de Inspiração (T.ins):", font=("Segoe UI", 11, "bold"), text_color="#17a2b8").pack(anchor="w", padx=10, pady=(6, 2))
    ins1_lbl = ctk.CTkLabel(results_frame, text="  1ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins1_lbl.pack(anchor="w", padx=10, pady=1)
    ins2_lbl = ctk.CTkLabel(results_frame, text="  2ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins2_lbl.pack(anchor="w", padx=10, pady=1)
    ins3_lbl = ctk.CTkLabel(results_frame, text="  3ª Inspiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    ins3_lbl.pack(anchor="w", padx=10, pady=1)

    # Seção 2: Expirações
    ctk.CTkLabel(results_frame, text="Tempos de Expiração (T.exp):", font=("Segoe UI", 11, "bold"), text_color="#28a745").pack(anchor="w", padx=10, pady=(6, 2))
    exp1_lbl = ctk.CTkLabel(results_frame, text="  1ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp1_lbl.pack(anchor="w", padx=10, pady=1)
    exp2_lbl = ctk.CTkLabel(results_frame, text="  2ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp2_lbl.pack(anchor="w", padx=10, pady=1)
    exp3_lbl = ctk.CTkLabel(results_frame, text="  3ª Expiração: Aguardando...", font=("Segoe UI", 11), text_color="#aaaaaa")
    exp3_lbl.pack(anchor="w", padx=10, pady=(1, 6))

    cancel_flag = {"cancel": False}

    def on_close():
        cancel_flag["cancel"] = True
        timing_win.destroy()

    timing_win.protocol("WM_DELETE_WINDOW", on_close)

    action_btn = ctk.CTkButton(main_f, text="Cancelar", fg_color="#631414", hover_color="#4a0f0f", height=30, command=on_close)
    action_btn.pack(pady=(6, 0))

    def calib_worker():
        ins_durations = []
        exp_durations = []

        ins_labels = [ins1_lbl, ins2_lbl, ins3_lbl]
        exp_labels = [exp1_lbl, exp2_lbl, exp3_lbl]

        # --- FASE 1: 3x MEDIÇÕES DE INSPIRAÇÃO ---
        for attempt in range(1, 4):
            if cancel_flag["cancel"]: return

            timing_win.after(0, lambda a=attempt: status_lbl.configure(text=f"Fase 1: Inspiração ({a}/3)", text_color="#17a2b8"))
            timing_win.after(0, lambda: instruction_lbl.configure(text="Prepare-se para puxar o ar..."))

            # Contagem de preparação (3s)
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                timing_win.after(0, lambda s=sec: timer_lbl.configure(text=f"{s}s", text_color="#ffc107"))
                time.sleep(1.0)

            if cancel_flag["cancel"]: return
            timing_win.after(0, lambda: instruction_lbl.configure(text="PUXE O AR EM RITMO REGULAR E CONTÍNUO!"))
            timing_win.after(0, lambda: timer_lbl.configure(text_color="#17a2b8"))

            # Captura de tempo ativo de inspiração (5s)
            start_time = time.time()
            in_phase = False
            cur_segment_start = 0.0
            max_cont_dur = 0.0

            while time.time() - start_time < 5.0:
                if cancel_flag["cancel"]: return
                now = time.time()
                rem = max(0.0, 5.0 - (now - start_time))
                timing_win.after(0, lambda r=rem: timer_lbl.configure(text=f"{r:.1f}s"))

                cur_flow = plot_data_flow[-1] if len(plot_data_flow) > 0 else 0.0

                if cur_flow < -3.0:
                    if not in_phase:
                        in_phase = True
                        cur_segment_start = now
                    else:
                        seg_dur = now - cur_segment_start
                        if seg_dur > max_cont_dur:
                            max_cont_dur = seg_dur
                else:
                    if in_phase:
                        in_phase = False

                time.sleep(0.02)

            measured_t = round(max_cont_dur, 2)
            if measured_t < 0.3:
                measured_t = 1.50 # fallback padrão caso paciente não tenha executado a manobra
            ins_durations.append(measured_t)

            res_text = f"  {attempt}ª Inspiração: {measured_t:.2f} s"
            lbl_w = ins_labels[attempt - 1]
            timing_win.after(0, lambda l=lbl_w, t=res_text: l.configure(text=t, text_color="#17a2b8"))

            # Intervalo de descanso (3s)
            timing_win.after(0, lambda: instruction_lbl.configure(text="Descanse um instante..."))
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                timing_win.after(0, lambda s=sec: timer_lbl.configure(text=f"Descanso: {s}s", text_color="#aaaaaa"))
                time.sleep(1.0)

        # --- FASE 2: 3x MEDIÇÕES DE EXPIRAÇÃO ---
        for attempt in range(1, 4):
            if cancel_flag["cancel"]: return

            timing_win.after(0, lambda a=attempt: status_lbl.configure(text=f"Fase 2: Expiração ({a}/3)", text_color="#28a745"))
            timing_win.after(0, lambda: instruction_lbl.configure(text="Prepare-se para soprar o ar..."))

            # Contagem de preparação (3s)
            for sec in range(3, 0, -1):
                if cancel_flag["cancel"]: return
                timing_win.after(0, lambda s=sec: timer_lbl.configure(text=f"{s}s", text_color="#ffc107"))
                time.sleep(1.0)

            if cancel_flag["cancel"]: return
            timing_win.after(0, lambda: instruction_lbl.configure(text="SOPRE O AR EM RITMO REGULAR E CONTÍNUO!"))
            timing_win.after(0, lambda: timer_lbl.configure(text_color="#28a745"))

            # Captura de tempo ativo de expiração (5s)
            start_time = time.time()
            in_phase = False
            cur_segment_start = 0.0
            max_cont_dur = 0.0

            while time.time() - start_time < 5.0:
                if cancel_flag["cancel"]: return
                now = time.time()
                rem = max(0.0, 5.0 - (now - start_time))
                timing_win.after(0, lambda r=rem: timer_lbl.configure(text=f"{r:.1f}s"))

                cur_flow = plot_data_flow[-1] if len(plot_data_flow) > 0 else 0.0

                if cur_flow > 3.0:
                    if not in_phase:
                        in_phase = True
                        cur_segment_start = now
                    else:
                        seg_dur = now - cur_segment_start
                        if seg_dur > max_cont_dur:
                            max_cont_dur = seg_dur
                else:
                    if in_phase:
                        in_phase = False

                time.sleep(0.02)

            measured_t = round(max_cont_dur, 2)
            if measured_t < 0.3:
                measured_t = 3.00 # fallback padrão caso paciente não tenha executado a manobra
            exp_durations.append(measured_t)

            res_text = f"  {attempt}ª Expiração: {measured_t:.2f} s"
            lbl_w = exp_labels[attempt - 1]
            timing_win.after(0, lambda l=lbl_w, t=res_text: l.configure(text=t, text_color="#28a745"))

            # Intervalo de descanso entre expirações (se não for a última)
            if attempt < 3:
                timing_win.after(0, lambda: instruction_lbl.configure(text="Descanse um instante..."))
                for sec in range(3, 0, -1):
                    if cancel_flag["cancel"]: return
                    timing_win.after(0, lambda s=sec: timer_lbl.configure(text=f"Descanso: {s}s", text_color="#aaaaaa"))
                    time.sleep(1.0)

        if cancel_flag["cancel"]: return

        avg_t_ins = round(sum(ins_durations) / 3.0, 2)
        avg_t_exp = round(sum(exp_durations) / 3.0, 2)
        ratio_val = round(avg_t_exp / avg_t_ins, 1) if avg_t_ins > 0 else 2.0
        ie_str = f"1:{ratio_val}"

        update_active_profile_metrics(t_in=avg_t_ins, t_ex=avg_t_exp, ie=ie_str)

        timing_win.after(0, lambda: status_lbl.configure(text="Aferição Concluída!", text_color="#28a745"))
        timing_win.after(0, lambda: instruction_lbl.configure(text=f"Médias Salvas: Ins = {avg_t_ins:.2f}s | Exp = {avg_t_exp:.2f}s | I:E {ie_str}"))
        timing_win.after(0, lambda: timer_lbl.configure(text="100%", text_color="#28a745"))
        timing_win.after(0, lambda: action_btn.configure(text="Salvar e Fechar", fg_color="#28a745", hover_color="#218838", command=timing_win.destroy))
        log(f"[Tempos Ins/Exp]: Concluída. T.Ins = {avg_t_ins:.2f}s | T.Exp = {avg_t_exp:.2f}s | I:E = {ie_str}.")

    threading.Thread(target=calib_worker, daemon=True).start()

def on_aferir_selected(choice):
    aferir_option.set("📊 Aferições ▾")
    if "Picos" in choice:
        start_peak_calibration()
    elif "Taxa" in choice:
        start_rate_calibration()
    elif "Tempos" in choice:
        start_timing_calibration()

aferir_option = ctk.CTkOptionMenu(
    header_top_row,
    values=["📊 Aferições ▾", "1. Picos (3 Ins + 3 Exp)", "2. Taxa Resp. (1 min)", "3. Tempos (Ins / Exp)"],
    width=175,
    height=28,
    font=("Segoe UI", 11, "bold"),
    fg_color="#1f538d",
    button_color="#14375e",
    command=on_aferir_selected
)
aferir_option.set("📊 Aferições ▾")
aferir_option.pack(side="right", padx=(5, 0))

info_btn = ctk.CTkButton(
    header_top_row,
    text="📋 Relatório",
    width=85,
    height=28,
    font=("Segoe UI", 11, "bold"),
    fg_color="#2b2b2b",
    hover_color="#3a3a3a",
    command=open_info_window
)
info_btn.pack(side="right", padx=(0, 5))

# Painel adicional: somente a observacao dos dados recebidos por USB/BLE.
# NAO modifica a via antiga de pressao/fluxo nem os calculos do Gate 01.
ppg_info_frame = ctk.CTkFrame(popup_header_frame, fg_color="transparent")
ppg_info_frame.pack(fill="x", padx=8, pady=(0, 8))
ppg_state_label = ctk.CTkLabel(
    ppg_info_frame, text="PPG: sem dados | Contato: -- | G1: -- | BPM: --",
    font=("Segoe UI", 12, "bold"), text_color="#e2e8f0", anchor="w")
ppg_state_label.pack(fill="x")
ppg_stats_label = ctk.CTkLabel(
    ppg_info_frame, text="Recebidas: 0 | 0 Hz | Perdas: 0 | Duplicadas: 0 | JSON invalido: 0",
    font=("Segoe UI", 11), text_color="#9ca3af", anchor="w")
ppg_stats_label.pack(fill="x")


def toggle_ppg_csv():
    """Opcional: registrar RAW completo, inclusive janelas reprovadas."""
    if ppg_monitor.csv.active:
        try:
            ppg_monitor.csv.stop()
            ppg_csv_btn.configure(text="Gravar CSV PPG")
            snap = ppg_monitor.snapshot()
            log(f"CSV PPG finalizado: {snap['csv_written']} linhas; "
                f"descartadas pelo gravador: {snap['csv_dropped']}.")
        except Exception as exc:
            log(f"Falha ao finalizar CSV PPG: {exc}")
        return
    initial = "pitaco24_ppg_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    target = filedialog.asksaveasfilename(
        parent=plot_window, title="Gravar dados brutos PPG/G1/pressao",
        initialfile=initial, defaultextension=".csv",
        filetypes=[("Dados CSV", "*.csv")])
    if not target:
        return
    try:
        ppg_monitor.csv.start(target)
        ppg_csv_btn.configure(text="Encerrar CSV PPG")
        log("Gravacao CSV PPG iniciada: " + target)
    except Exception as exc:
        log(f"Falha ao abrir gravacao CSV: {exc}")


ppg_csv_btn = ctk.CTkButton(
    ppg_info_frame, text="Gravar CSV PPG", width=135, height=26,
    command=toggle_ppg_csv)
ppg_csv_btn.pack(anchor="e", pady=(2, 0))

show_pressure_var = ctk.BooleanVar(value=True)

fig, (ax1, ax_ppg) = plt.subplots(2, 1, figsize=(8, 6), dpi=100,
                                 gridspec_kw={"height_ratios": (1, 1.15)})
fig.subplots_adjust(hspace=0.42, left=0.10, right=0.90, top=0.96, bottom=0.10)
fig.patch.set_facecolor('#2b2b2b') 
ax1.set_facecolor('#2b2b2b')

ax1.set_ylabel('Fluxo (L/min)', color='#ffffff')
ax1.tick_params(axis='x', colors='white')
ax1.tick_params(axis='y', colors='#ffffff')

ax1.minorticks_on()
ax1.grid(True, which='major', linestyle='-', linewidth=0.8, color='#555555')
ax1.grid(True, which='minor', linestyle=':', linewidth=0.5, color='#444444')

line_flow, = ax1.plot(plot_data_flow, color='#ffffff', label='Fluxo', linewidth=2)
hline_max = ax1.axhline(y=persistent_max_flow, color='#28a745', linestyle='--', linewidth=1.5, alpha=0.85, label='Máx')
hline_min = ax1.axhline(y=persistent_min_flow, color='#17a2b8', linestyle='--', linewidth=1.5, alpha=0.85, label='Mín')

ax2 = ax1.twinx()
ax2.set_ylabel('Pressão (Pa)', color='#ffffff')
ax2.tick_params(axis='y', colors='#ffffff')
ax2.yaxis.set_visible(False)

# RED/IR sao RAW (contagens do ADC) sem qualquer filtro aplicado pelo middleware.
ax_ppg.set_facecolor("#2b2b2b")
ax_ppg.set_ylabel("PPG RAW (contagens)", color="white")
ax_ppg.set_xlabel("Tempo do dispositivo (s)", color="white")
ax_ppg.tick_params(axis="x", colors="white")
ax_ppg.tick_params(axis="y", colors="white")
ax_ppg.grid(True, color="#555555", linestyle=":", alpha=0.8)
line_red, = ax_ppg.plot([], [], color="#ef4444", linewidth=1.5, label="RED")
line_ir, = ax_ppg.plot([], [], color="#38bdf8", linewidth=1.5, label="IR")
ax_ppg.legend(loc="upper right", facecolor="#2b2b2b",
              edgecolor="#555555", labelcolor="white", fontsize=9)

canvas = FigureCanvasTkAgg(fig, master=plot_window)
canvas_widget = canvas.get_tk_widget()
canvas_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

def update_plot(frame):
    if is_plotting:
        latest_flow = plot_data_flow[-1] if len(plot_data_flow) > 0 else 0.0
        current_val_label.configure(text=f"Fluxo: {latest_flow:.2f} L/min")

        line_flow.set_ydata(plot_data_flow)
        hline_max.set_ydata([persistent_max_flow, persistent_max_flow])
        hline_min.set_ydata([persistent_min_flow, persistent_min_flow])

        all_vals = list(plot_data_flow) + [persistent_max_flow, persistent_min_flow]
        f_min, f_max = min(all_vals), max(all_vals)
        f_pad = max(5.0, (f_max - f_min) * 0.1) 
        f_lower, f_upper = f_min - f_pad, f_max + f_pad
        ax1.set_ylim(f_lower, f_upper)
        
        if show_pressure_var.get():
            ax2.yaxis.set_visible(True)
            ax2.set_ylim(flow_to_pressure(f_lower), flow_to_pressure(f_upper))
        else:
            ax2.yaxis.set_visible(False) 
        # A GUI apenas desenha um snapshot. As threads BLE/USB registram
        # no modelo e jamais chamam metodos Tk ou Matplotlib diretamente.
        snap = ppg_monitor.snapshot()
        history = snap["history"]
        if history:
            xs, red_values, ir_values = zip(*history)
            line_red.set_data(xs, red_values)
            line_ir.set_data(xs, ir_values)
            xmax = xs[-1]
            ax_ppg.set_xlim(xmax - 12.0, xmax + .25)
            finite = [v for rec in history for v in rec[1:]
                      if isinstance(v, (float, int)) and math.isfinite(v)]
            if finite:
                lo, hi = min(finite), max(finite)
                pad = max(150.0, (hi - lo) * .12)
                ax_ppg.set_ylim(max(0.0, lo - pad), hi + pad)
        else:
            line_red.set_data([], [])
            line_ir.set_data([], [])
        contact = {True: "presente", False: "ausente"}.get(snap["contact"], "--")
        g1_state = {True: "PASS", False: "REPROVADO"}.get(snap["g1_effective"], "aguardando")
        bpm_text = f"{snap['bpm']:.1f}" if snap["bpm"] is not None else "--"
        ppg_state_label.configure(
            text=(f"PPG {snap['source'] or '--'} | Contato: {contact} | "
                  f"G1: {g1_state} (motivo {snap['reason']}) | BPM: {bpm_text}"))
        ppg_stats_label.configure(
            text=(f"Recebidas: {snap['samples']} | {snap['sample_rate']:.1f} Hz | "
                  f"Perdas seq: {snap['missing']} | Duplicadas: {snap['duplicates']} | "
                  f"JSON inválido: {snap['invalid_json']} | "
                  f"Janelas G1: {snap['g1_windows']} "
                  f"(PASS {snap['g1_passes']}, falha {snap['g1_failures']}) | "
                  f"Pressão: {snap['pressure_messages']} | "
                  f"CSV descartadas: {snap['csv_dropped']}"))
        canvas.draw()
    return line_flow, line_red, line_ir,

# Redesenho ~7 Hz: aquisição continua ~25 Hz em outra thread.
# Menor carga Tk/Matplotlib reduz a chance de criar gaps no proprio testador.
ani = animation.FuncAnimation(fig, update_plot, interval=150, blit=False, cache_frame_data=False)

# --- LOGICA DE COMUNICACAO ---
buffer = bytearray()

def update_pressure_from_device(val_pa):
    """Mesmo caminho antigo da pressao, usado por USB e BLE."""
    global last_value, target_value, last_update_time
    raw_flow = calculate_flow(val_pa)
    filtered_flow = pressure_filter.process(raw_flow)
    plot_data_pressure.append(val_pa)
    plot_data_flow.append(filtered_flow)
    last_value = target_value
    target_value = output_for_unity(val_pa, filtered_flow)
    last_update_time = time.time()


def process_pitaco_line(line_str, allow_pressure=True, source="USB"):
    """Aceita pressao original/JSON 2.4 e registra PPG para o monitor."""
    global last_oxi_sent
    msg = parse_pitaco_line(line_str)
    if msg is None:
        return False
    kind = msg.get("type")
    ppg_monitor.observe(msg, source=source)
    if kind == "pressure":
        if allow_pressure:
            update_pressure_from_device(msg["mpx5010dp"]["pressure_pa"])
        return True
    if kind == "g1":
        return True
    if kind != "sample":
        return False

    pressure = msg.get("mpx5010dp")
    if allow_pressure and isinstance(pressure, dict) and pressure.get("valid") is True:
        pa = pressure.get("pressure_pa")
        if isinstance(pa, (float, int)) and not isinstance(pa, bool) and math.isfinite(pa):
            update_pressure_from_device(float(pa))

    ppg = msg.get("ppg")
    sqi = msg.get("sqi")
    if not isinstance(ppg, dict) or not isinstance(sqi, dict):
        return True
    bpm = ppg.get("bpm")
    # Gate 01 PASS, BPM valido e porta virtual do oxímetro habilitada.
    if (ppg.get("bpm_valid") is True and sqi.get("g1") is True
            and isinstance(bpm, (int, float)) and not isinstance(bpm, bool)
            and math.isfinite(bpm) and 35 <= bpm <= 200
            and oxi_sampling and ser_oxi and ser_oxi.is_open
            and time.monotonic() - last_oxi_sent >= 1.0):
        # Contrato de jogo original: "FC,SpO2". Zero = SpO2 INDISPONIVEL,
        # nao uma estimativa calculada. Em UI atual pode aparecer como 0%.
        try:
            ser_oxi.write(f"{round(bpm)},0\r\n".encode("ascii"))
            last_oxi_sent = time.monotonic()
        except serial.SerialException as exc:
            log(f"Falha no envio de BPM para Unity: {exc}")
    return True


def ppg_notification_handler(sender, data):
    # Uma notificacao pode ter apenas fragmentos do mesmo JSON; mede frames
    # completos e erros SEM inventar amostras que nao chegaram.
    ppg_monitor.note_ble_fragment()
    for line_str in ble_ppg_lines.feed(bytes(data)):
        try:
            if not process_pitaco_line(line_str, allow_pressure=False, source="BLE"):
                ppg_monitor.note_invalid_json()
        except Exception as exc:
            ppg_monitor.note_invalid_json()
            log(f"Erro ao interpretar JSON PPG BLE: {exc}")


def oximeter_command_loop():
    """Responde echox aos comandos da COM virtual sem mexer no PITACO legado."""
    global oxi_sampling, running
    while running:
        try:
            if not ser_oxi or not ser_oxi.is_open:
                break
            data = ser_oxi.read(ser_oxi.in_waiting or 1)
            for cmd in data.lower():
                if cmd == ord("e"):
                    ser_oxi.write(b"echox\r\n")
                elif cmd == ord("r"):
                    oxi_sampling = True
                    # O jogo de oximetria pode iniciar sozinho a aquisicao.
                    if ser_device and ser_device.is_open:
                        ser_device.write(b"r")
                    elif client and client.is_connected and ble_loop:
                        asyncio.run_coroutine_threadsafe(
                            client.write_gatt_char(CHARACTERISTIC_UUID, b"r", response=True),
                            ble_loop)
                elif cmd == ord("f"):
                    oxi_sampling = False
        except Exception as exc:
            if running:
                log(f"Erro no canal virtual do oxímetro: {exc}")
            break


def notification_handler(sender, data):
    global buffer, last_value, target_value, last_update_time
    try:
        for byte in data:
            if byte == ord('\n'):
                line_str = buffer.decode('ascii').strip()
                
                if line_str.startswith("zero_"):
                    root.after(0, lambda msg=line_str: (log("[BLE <- ESP32] " + msg), zero_status(msg)))
                elif line_str == "echop":
                    if ser and ser.is_open:
                        ser.write(b"echop\r\n")
                else:
                    # Se não for echo, trata como número de pressão (Pa)
                    try:
                        process_pitaco_line(line_str, allow_pressure=True, source="BLE")
                    except ValueError:
                        pass
                    
                buffer.clear()
            else:
                buffer.append(byte)
    except Exception as e:
        log(f"[Erro de Notify] {e}")

def interpolation_loop():
    global last_value, target_value, last_update_time, running, ser, is_sampling
    output_interval = 0.01 
    while running:
        if is_sampling and ser and ser.is_open: 
            now = time.time()
            elapsed = now - last_update_time
            fraction = min(elapsed / update_interval, 1.0)
            interpolated_val = last_value + (target_value - last_value) * fraction
            
            line = f"{interpolated_val:.2f}\r\n".encode('ascii')
            try:
                ser.write(line)
            except:
                pass
        
        time.sleep(output_interval)

def serial_read_loop():
    global running, ser, ser_device, client, ble_loop, is_sampling
    try:
        while running:
            if ser and ser.is_open and ser.in_waiting:
                data = ser.read(ser.in_waiting)
                if data:
                    try:
                        decoded = data.decode('ascii', errors='ignore').strip()
                        decoded_lower = decoded.lower()
                        
                        if 'r' in decoded_lower:
                            is_sampling = True
                        elif 'f' in decoded_lower or 'e' in decoded_lower:
                            is_sampling = False
                            
                        if decoded:
                            log(f"[Jogo -> PITACO]: Comando '{decoded}' enviado.")
                    except Exception:
                        pass

                    # Se conectado via BLE, repassa por BLE
                    if client and client.is_connected:
                        fut = asyncio.run_coroutine_threadsafe(
                            client.write_gatt_char(CHARACTERISTIC_UUID, data, False),
                            ble_loop
                        )
                        try:
                            fut.result(timeout=5)
                        except Exception as e:
                            log(f"Erro escrita BLE: {e}")

                    # Se conectado via USB, repassa para a porta USB física do ESP32
                    elif ser_device and ser_device.is_open:
                        try:
                            ser_device.write(data)
                        except Exception as e:
                            log(f"Erro escrita USB ESP32: {e}")
            else:
                threading.Event().wait(0.01)
    except Exception as e:
        log(f"Erro leitura serial: {e}")

def usb_read_device_loop():
    global running, ser, ser_device, last_value, target_value, last_update_time
    usb_buffer = bytearray()
    try:
        while running and ser_device and ser_device.is_open:
            if ser_device.in_waiting:
                data = ser_device.read(ser_device.in_waiting)
                for byte in data:
                    if byte == ord('\n'):
                        line_str = usb_buffer.decode('ascii', errors='ignore').strip()
                        if line_str.startswith("zero_"):
                            root.after(0, lambda msg=line_str: (log("[USB <- ESP32] " + msg), zero_status(msg)))
                        elif line_str == "echop":
                            if ser and ser.is_open:
                                ser.write(b"echop\r\n")
                        else:
                            try:
                                process_pitaco_line(line_str, allow_pressure=True, source="USB")
                            except ValueError:
                                pass
                        usb_buffer.clear()
                    else:
                        usb_buffer.append(byte)
            else:
                threading.Event().wait(0.005)
    except Exception as e:
        log(f"Erro na leitura do ESP32 via USB: {e}")

async def ble_bridge():
    global client, running, ser, is_sampling
    log("Procurando pelo PITACO via BLE...")
    
    def handle_disconnect(client_instance):
        if running:
            log("Aviso: Conexão BLE perdida!")
            root.after(0, stop_bridge)

    try:
        devices = await BleakScanner.discover(timeout=5.0)
        pitaco = next((d for d in devices if d.name == DEVICE_NAME), None)
            
        if pitaco is None:
            log("PITACO não encontrado na busca BLE.")
            root.after(0, stop_bridge)
            return

        log(f"Conectando ao PITACO ({pitaco.address})...")
        client = BleakClient(pitaco.address, disconnected_callback=handle_disconnect)

        await client.connect()
        log("PITACO conectado via BLE. Aguardando comandos.")
        
        root.after(0, lambda: set_indicator(status_ble, True))
        root.after(0, lambda: calib_btn.configure(state="normal"))
        root.after(0, lambda: zero_btn.configure(state="normal"))
        root.after(0, lambda: graph_btn.configure(state="normal"))
        root.after(0, lambda: ppg_graph_btn.configure(state="normal"))

        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        ble_ppg_lines.reset()
        ppg_notify_active = False
        try:
            await client.start_notify(PPG_NOTIFY_UUID, ppg_notification_handler)
            ppg_notify_active = True
            log("Canal PPG/JSON BLE ativo.")
        except Exception as e:
            log(f"Canal PPG/JSON BLE nao disponivel: {e}")
        if not (ser and ser.is_open):
            # Em monitor sem Unity, cliente inicia a leitura.
            await client.write_gatt_char(CHARACTERISTIC_UUID, b'e', response=True)
            await client.write_gatt_char(CHARACTERISTIC_UUID, b'r', response=True)
            is_sampling = True

        while running and client.is_connected:
            await asyncio.sleep(0.1)

        if client.is_connected:
            if ppg_notify_active:
                await client.stop_notify(PPG_NOTIFY_UUID)
            await client.stop_notify(CHARACTERISTIC_UUID)
            await client.disconnect()

    except Exception as e:
        log(f"Erro BLE: {e}")
        if running:
            root.after(0, stop_bridge)
    finally:
        root.after(0, lambda: set_indicator(status_ble, False))
        root.after(0, lambda: calib_btn.configure(state="disabled"))
        root.after(0, lambda: zero_btn.configure(state="disabled"))
        root.after(0, lambda: graph_btn.configure(state="disabled"))
        root.after(0, lambda: ppg_graph_btn.configure(state="disabled"))

def start_bridge():
    global running, ser, ser_oxi, ser_device, ble_loop, ble_loop_thread, is_sampling, oxi_sampling

    if running: return
    ppg_monitor.reset()  # nao misturar sessoes USB, BLE ou reconexoes
    
    mode = conn_mode_var.get()
    game_port = port_var.get()
    if game_port == "Somente monitor":
        game_port = ""
    ser = None
    ser_oxi = None
    ser_device = None
    oxi_sampling = False
    
    if game_port:
        if not game_port.startswith("\\\\.\\"):
            game_port = "\\\\.\\{}".format(game_port)
        try:
            ser = serial.Serial(game_port, BAUDRATE, timeout=0)
            log(f"Serial do Jogo conectada em {game_port}.")
            set_indicator(status_serial, True)
        except Exception as e:
            log(f"Aviso: Falha ao abrir porta do jogo {game_port}. Rodando como Monitor.")
            set_indicator(status_serial, False)
    else:
        log("Aviso: Nenhuma porta do jogo selecionada. Rodando como Monitor.")
        set_indicator(status_serial, False)

    oxi_port = oxi_port_var.get()
    if oxi_port and oxi_port != "Somente monitor":
        if oxi_port == port_var.get() or oxi_port == device_port_var.get():
            log("Oxímetro: porta conflita com a porta de pressão ou do dispositivo.")
        else:
            try:
                oxi_serial_name = oxi_port if oxi_port.startswith("\\\\.\\") else "\\\\.\\{}".format(oxi_port)
                ser_oxi = serial.Serial(oxi_serial_name, BAUDRATE, timeout=0.1)
                log(f"Porta virtual Oxímetro conectada: {oxi_port}")
            except Exception as e:
                log(f"Falha ao abrir a COM virtual do oxímetro: {e}")
    
    running = True
    bridge_btn.configure(text="Desconectar", fg_color="#dc3545", hover_color="#c82333")
    refresh_btn.configure(state="disabled")
    port_combo.configure(state="disabled")
    oxi_port_combo.configure(state="disabled")
    device_port_combo.configure(state="disabled")
    conn_mode_segmented.configure(state="disabled")

    if mode == "Bluetooth":
        log("Iniciando conexão sem fio (Bluetooth)...")
        ble_loop = asyncio.new_event_loop()

        def run_ble_loop():
            asyncio.set_event_loop(ble_loop)
            try:
                ble_loop.run_until_complete(ble_bridge())
            finally:
                ble_loop.close()

        ble_loop_thread = threading.Thread(target=run_ble_loop, daemon=True)
        ble_loop_thread.start()
    else:
        # Modo Cabo USB
        dev_port = device_port_var.get()
        if dev_port:
            if not dev_port.startswith("\\\\.\\"):
                dev_port = "\\\\.\\{}".format(dev_port)
            try:
                ser_device = serial.Serial(dev_port, BAUDRATE, timeout=0)
                log(f"Conectado ao ESP32 via USB na porta física {dev_port}.")
                set_indicator(status_ble, True)
                calib_btn.configure(state="normal")
                zero_btn.configure(state="normal")
                graph_btn.configure(state="normal")
                ppg_graph_btn.configure(state="normal")
                threading.Thread(target=usb_read_device_loop, daemon=True).start()
                if not (ser and ser.is_open):
                    # Teste sem Unity: solicitar identificacao e aquisicao ao ESP32.
                    ser_device.write(b'e')
                    ser_device.write(b'r')
                    is_sampling = True
                    log("[USB] Monitor: comandos e/r enviados, aguardando pressao.")
            except Exception as e:
                log(f"Erro ao abrir porta USB do ESP32 ({dev_port}): {e}")
                root.after(0, stop_bridge)
                return
        else:
            log("Erro: Nenhuma porta USB do ESP32 selecionada!")
            root.after(0, stop_bridge)
            return

    threading.Thread(target=serial_read_loop, daemon=True).start()
    threading.Thread(target=interpolation_loop, daemon=True).start()
    if ser_oxi:
        threading.Thread(target=oximeter_command_loop, daemon=True).start()

def stop_bridge():
    global running, ser, ser_oxi, ser_device, is_sampling, oxi_sampling

    if not running: return

    running = False
    is_sampling = False
    oxi_sampling = False
    
    bridge_btn.configure(text="Conectar", fg_color="#28a745", hover_color="#218838")
    refresh_btn.configure(state="normal")
    port_combo.configure(state="normal")
    oxi_port_combo.configure(state="normal")
    device_port_combo.configure(state="normal")
    conn_mode_segmented.configure(state="normal")
    calib_btn.configure(state="disabled")
    zero_btn.configure(state="disabled")
    graph_btn.configure(state="disabled")
    ppg_graph_btn.configure(state="disabled")
    set_indicator(status_serial, False)
    set_indicator(status_ble, False)

    if is_plotting:
        close_graph()
    if is_ppg_plotting:
        close_ppg_graph()

    log("Desconectando...")
    if ppg_monitor.csv.active:
        try:
            ppg_monitor.csv.stop()
            ppg_csv_btn.configure(text="Gravar CSV PPG")
            log(f"CSV PPG salvo: {ppg_monitor.csv.written} linhas; "
                f"descartadas {ppg_monitor.csv.dropped}.")
        except Exception as exc:
            log(f"Falha ao encerrar CSV PPG: {exc}")
    # Encerra aquisicao no modo Cabo USB, inclusive monitor sem Unity.
    if ser_device and ser_device.is_open:
        try:
            ser_device.write(b'f')
        except Exception:
            pass

    try:
        if ser and ser.is_open:
            ser.close()
            log("Porta COM do jogo fechada.")
    except Exception as e:
        log(f"Erro fechando COM do jogo: {e}")

    try:
        if ser_device and ser_device.is_open:
            ser_device.close()
            log("Porta USB do ESP32 fechada.")
    except Exception as e:
        log(f"Erro fechando USB ESP32: {e}")

    try:
        if ser_oxi and ser_oxi.is_open:
            ser_oxi.close()
            log("Porta virtual do oxímetro fechada.")
    except Exception as exc:
        log(f"Erro fechando COM oxímetro: {exc}")

    log("Desconectado.")

def on_exit():
    stop_bridge()
    root.destroy()
    sys.exit(0)

refresh_ports() 
root.protocol("WM_DELETE_WINDOW", on_exit) 
root.mainloop()