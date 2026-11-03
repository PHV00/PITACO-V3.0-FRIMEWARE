
import os
import sys
import subprocess
from tkinter import messagebox, Menu, filedialog
import customtkinter as ctk
import serial
import threading
import ctypes
import asyncio
import time
import struct
import json
from ..protocol import parse_pitaco_line, BleJsonlBuffer
from ..monitor import PpgMonitor
from ..configuration import get_config_path, DEFAULT_PROFILE_DATA, DEFAULT_CONFIG, load_config
from ..ports import get_all_com_ports
from .. import pneumo
from ..pneumo import parse_pressure_pa, calculate_flow, flow_to_pressure, PressureFilter
import tempfile
import urllib.request
import urllib.error
import esptool
from collections import deque
from bleak import BleakClient, BleakScanner
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

import datetime
import math


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
        "scale_multiplier": pneumo.flow_multiplier,
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


MAX_POINTS = 100
plot_data_pressure = deque([0.0]*MAX_POINTS, maxlen=MAX_POINTS)
plot_data_flow = deque([0.0]*MAX_POINTS, maxlen=MAX_POINTS)
is_plotting = False
is_ppg_plotting = False



def output_for_unity(pressure_pa, estimated_flow):
    selected = output_mode_var.get() if 'output_mode_var' in globals() else "Pressão relativa (Pa)"
    return pressure_pa if selected == "Pressão relativa (Pa)" else estimated_flow




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
    was_active = is_ppg_plotting
    is_plotting = True
    plot_window.deiconify()
    graph_btn.configure(state="disabled")
    if not was_active and not is_sampling:
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
    was_active = is_plotting
    is_ppg_plotting = True
    ppg_window.deiconify()
    ppg_graph_btn.configure(state="disabled")
    if not was_active and not is_sampling:
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
    pneumo.flow_multiplier = val
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


# As duas janelas compartilham a conexão e os dados deste módulo.
# Apenas elementos visuais são instanciados nas views.
from .pneumo_view import create_pneumo_view
from .oxy_and_cardio_view import create_oxy_and_cardio_view

pneumo_view = create_pneumo_view(sys.modules[__name__])
plot_window = pneumo_view.window
profile_badge_label = pneumo_view.profile_badge_label
current_val_label = pneumo_view.current_val_label
max_val_label = pneumo_view.max_val_label
min_val_label = pneumo_view.min_val_label
rate_val_label = pneumo_view.rate_val_label
timing_val_label = pneumo_view.timing_val_label
open_info_window = pneumo_view.open_info_window
start_peak_calibration = pneumo_view.start_peak_calibration
start_rate_calibration = pneumo_view.start_rate_calibration
start_timing_calibration = pneumo_view.start_timing_calibration
update_plot = pneumo_view.update_plot

oxy_and_cardio_view = create_oxy_and_cardio_view(sys.modules[__name__])
ppg_window = oxy_and_cardio_view.window
ppg_csv_btn = oxy_and_cardio_view.csv_button
toggle_ppg_experiment = oxy_and_cardio_view.toggle_ppg_experiment
toggle_ppg_csv = oxy_and_cardio_view.toggle_ppg_csv
update_ppg_plot = oxy_and_cardio_view.update_ppg_plot

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
    set_indicator(status_serial, False)
    set_indicator(status_ble, False)

    if is_plotting:
        close_graph()
    if is_ppg_plotting:
        close_ppg_graph()
    # close_* habilita o botao de abertura; apos desconectar ambos precisam
    # permanecer desabilitados, ate a proxima conexao BLE/USB.
    graph_btn.configure(state="disabled")
    ppg_graph_btn.configure(state="disabled")

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

def run_gui():
    root.mainloop()

if __name__ == "__main__":
    run_gui()
