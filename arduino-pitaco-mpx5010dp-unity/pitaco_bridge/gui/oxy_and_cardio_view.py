"""Monitor cardíaco: PPG RED/IR, BPM FW/Python, SpO2 demo e CSV.

Somente apresentação e controles já existentes; a análise continua
em monitor.py / experimental.py. Sem conexão BLE própria.
"""
import datetime
import math
from types import SimpleNamespace
from tkinter import filedialog

import customtkinter as ctk
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


def create_oxy_and_cardio_view(app):
    """Monta a janela óptica utilizando os dados da conexão compartilhada."""
    root = app.root
    close_ppg_graph = app.close_ppg_graph
    ppg_monitor = app.ppg_monitor
    log = app.log

    # Painel optico em janela separada; o pneumografo permanece original.
    ppg_window = ctk.CTkToplevel(root)
    ppg_window.title("PITACO 2.4 - Monitor cardíaco e oximetria")
    ppg_window.geometry("920x790")
    ppg_window.protocol("WM_DELETE_WINDOW", close_ppg_graph)
    ppg_window.withdraw()

    ppg_info_frame = ctk.CTkFrame(ppg_window, fg_color="#1f1f1f", corner_radius=6)
    ppg_info_frame.pack(fill="x", padx=12, pady=(10, 5))

    ppg_state_label = ctk.CTkLabel(
        ppg_info_frame, text="PPG: sem dados | Contato: -- | G1: -- | BPM: --",
        font=("Segoe UI", 12, "bold"), text_color="#e2e8f0", anchor="w")
    ppg_state_label.pack(fill="x", padx=10, pady=(8, 1))

    spo2_state_label = ctk.CTkLabel(
        ppg_info_frame,
        text="SpO₂: não calculada (RED e IR brutos; sem estimativa validada)",
        font=("Segoe UI", 12, "bold"), text_color="#fbbf24", anchor="w")
    spo2_state_label.pack(fill="x", padx=10)


    def toggle_ppg_experiment():
        """Liga calculos de bancada no PC; nao envia seus valores para Unity."""
        ppg_monitor.set_experimental_enabled(ppg_experiment_var.get())


    ppg_experiment_var = ctk.BooleanVar(value=False)
    ppg_experiment_checkbox = ctk.CTkCheckBox(
        ppg_info_frame, variable=ppg_experiment_var,
        text="Calcular BPM e SpO₂ experimentais NO PYTHON (não calibrados)",
        text_color="#fbbf24", command=toggle_ppg_experiment)
    ppg_experiment_checkbox.pack(anchor="w", padx=12, pady=(6, 0))

    ppg_exp_status_label = ctk.CTkLabel(
        ppg_info_frame,
        text="Modo experimental: DESLIGADO | BPM Python: -- | R: --",
        font=("Segoe UI", 11), text_color="#fbbf24", anchor="w")
    ppg_exp_status_label.pack(fill="x", padx=10, pady=(0, 2))

    ppg_stats_label = ctk.CTkLabel(
        ppg_info_frame, text="Recebidas: 0 | Perdas: 0 | G1: 0 | CSV: 0",
        font=("Segoe UI", 11), text_color="#9ca3af", anchor="w", wraplength=860)
    ppg_stats_label.pack(fill="x", padx=10, pady=(1, 4))


    def toggle_ppg_csv():
        """CSV optico inclui amostras recusadas pelo G1 e contato ausente."""
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
            parent=ppg_window, title="Gravar dados brutos PPG/G1/pressao",
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
    ppg_csv_btn.pack(anchor="e", padx=12, pady=(2, 8))

    ppg_fig = Figure(figsize=(8, 6.3), dpi=100)
    ppg_grid = ppg_fig.add_gridspec(3, 1, height_ratios=(1.7, 0.95, 0.85))
    ax_ppg = ppg_fig.add_subplot(ppg_grid[0])
    ax_bpm = ppg_fig.add_subplot(ppg_grid[1], sharex=ax_ppg)
    ax_spo2 = ppg_fig.add_subplot(ppg_grid[2], sharex=ax_ppg)
    ppg_fig.patch.set_facecolor("#2b2b2b")
    ppg_fig.subplots_adjust(hspace=0.24, left=0.11, right=0.96,
                             top=0.96, bottom=0.085)
    for optical_axis in (ax_ppg, ax_bpm, ax_spo2):
        optical_axis.set_facecolor("#2b2b2b")
        optical_axis.tick_params(axis="x", colors="white")
        optical_axis.tick_params(axis="y", colors="white")
        optical_axis.grid(True, color="#555555", linestyle=":", alpha=0.8)

    ax_ppg.set_ylabel("PPG RAW (contagens)", color="white")
    line_red, = ax_ppg.plot([], [], color="#ef4444", linewidth=1.6, label="RED")
    line_ir, = ax_ppg.plot([], [], color="#38bdf8", linewidth=1.6, label="IR")
    ax_ppg.legend(loc="upper right", facecolor="#2b2b2b",
                  edgecolor="#555555", labelcolor="white", fontsize=9)

    ax_bpm.set_ylabel("BPM", color="white")
    ax_bpm.set_ylim(30, 205)
    line_bpm, = ax_bpm.plot([], [], color="#a78bfa", linewidth=1.8,
                            marker=".", markersize=3, label="FW qualificado")
    line_bpm_exp, = ax_bpm.plot([], [], color="#fbbf24", linewidth=1.6,
                                marker=".", markersize=3, label="Python EXP.")
    ax_bpm.legend(loc="upper right", facecolor="#2b2b2b",
                  edgecolor="#555555", labelcolor="white", fontsize=8)

    # Leitura instantanea bem visivel, no canto do proprio grafico de FC.
    # Sao fontes diferentes: nunca promover estimativa Python a valor firmware.
    bpm_fw_corner = ax_bpm.text(
        0.018, 0.96, "ESP32: -- BPM", transform=ax_bpm.transAxes,
        va="top", ha="left", fontsize=12, fontweight="bold",
        color="#a78bfa",
        bbox=dict(facecolor="#202020", edgecolor="#555555",
                  boxstyle="round,pad=0.35", alpha=0.93))
    bpm_py_corner = ax_bpm.text(
        0.018, 0.72, "Python EXP.: -- BPM", transform=ax_bpm.transAxes,
        va="top", ha="left", fontsize=12, fontweight="bold",
        color="#fbbf24",
        bbox=dict(facecolor="#202020", edgecolor="#555555",
                  boxstyle="round,pad=0.35", alpha=0.93))

    ax_spo2.set_ylabel("SpO₂ EXP. (%)", color="white")
    ax_spo2.set_xlabel("Tempo do dispositivo (s)", color="white")
    ax_spo2.set_ylim(70, 101)
    line_spo2_exp, = ax_spo2.plot([], [], color="#34d399",
                                 linewidth=1.5, marker=".", markersize=3,
                                 label="Não calibrada")
    ax_spo2.legend(loc="upper right", facecolor="#2b2b2b",
                   edgecolor="#555555", labelcolor="white", fontsize=8)

    ppg_canvas = FigureCanvasTkAgg(ppg_fig, master=ppg_window)
    ppg_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_ppg_plot(_frame):
        """Compara FW e algoritmo Python sem executar calculos na thread Tk."""
        if not app.is_ppg_plotting:
            return line_red, line_ir, line_bpm, line_bpm_exp, line_spo2_exp

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

        bpm_history = snap["bpm_history"]
        if bpm_history:
            line_bpm.set_data([x for x, _ in bpm_history],
                              [b for _, b in bpm_history])
        else:
            line_bpm.set_data([], [])

        experimental = snap["experimental"]
        if experimental["enabled"]:
            if experimental["bpm_history"]:
                xs_py, ys_py = zip(*experimental["bpm_history"])
                line_bpm_exp.set_data(xs_py, ys_py)
            else:
                line_bpm_exp.set_data([], [])
            if experimental["spo2_history"]:
                xs_spo2, ys_spo2 = zip(*experimental["spo2_history"])
                line_spo2_exp.set_data(xs_spo2, ys_spo2)
            else:
                line_spo2_exp.set_data([], [])
            py_bpm = (f"{experimental['bpm']:.1f}"
                      if experimental["bpm"] is not None else "--")
            py_ratio = (f"{experimental['ratio']:.3f}"
                        if experimental["ratio"] is not None else "--")
            spo2_text = (f"{experimental['spo2']:.1f}%"
                         if experimental["spo2"] is not None else "--")
            ppg_exp_status_label.configure(
                text=(f"BPM Python EXP.: {py_bpm} | Índice R: {py_ratio} | "
                      f"Estado: {experimental['status']}"))
            spo2_state_label.configure(
                text=(f"SpO₂ EXPERIMENTAL: {spo2_text} | "
                      "NÃO CALIBRADA / NÃO VALIDADA — NÃO USAR CLINICAMENTE"))
        else:
            line_bpm_exp.set_data([], [])
            line_spo2_exp.set_data([], [])
            ppg_exp_status_label.configure(
                text="Modo experimental: DESLIGADO | BPM Python: -- | R: --")
            spo2_state_label.configure(
                text="SpO₂: não calculada (RED e IR brutos; sem estimativa validada)")

        contact = {True: "presente", False: "ausente"}.get(snap["contact"], "--")
        g1_state = {True: "PASS", False: "REPROVADO"}.get(snap["g1_effective"], "aguardando")
        bpm_text = f"{snap['bpm']:.1f}" if snap["bpm"] is not None else "--"
        bpm_fw_corner.set_text(f"ESP32: {bpm_text} BPM")
        bpm_py_corner.set_text(
            f"Python EXP.: {py_bpm if experimental['enabled'] else '--'} BPM")
        ppg_state_label.configure(
            text=(f"PPG {snap['source'] or '--'} | Contato: {contact} | "
                  f"G1: {g1_state} (motivo {snap['reason']}) | "
                  f"BPM FW: {bpm_text} | {snap['fw_bpm_status']}"))
        ppg_stats_label.configure(
            text=(f"Recebidas: {snap['samples']} | {snap['sample_rate']:.1f} Hz | "
                  f"Perdas seq: {snap['missing']} | Duplicadas: {snap['duplicates']} | "
                  f"JSON inválido: {snap['invalid_json']} | "
                  f"Janelas G1: {snap['g1_windows']} "
                  f"(PASS {snap['g1_passes']}, falha {snap['g1_failures']}) | "
                  f"Pressão: {snap['pressure_messages']} | "
                  f"CSV descartadas: {snap['csv_dropped']}"))
        ppg_canvas.draw()
        return line_red, line_ir, line_bpm, line_bpm_exp, line_spo2_exp


    # Apenas redesenho ~7 Hz. Coleta BLE/USB ocorre em outras threads.
    ani_ppg = animation.FuncAnimation(ppg_fig, update_ppg_plot, interval=150,
                                      blit=False, cache_frame_data=False)

    return SimpleNamespace(
        window=ppg_window,
        csv_button=ppg_csv_btn,
        experiment_checkbox=ppg_experiment_checkbox,
        toggle_ppg_experiment=toggle_ppg_experiment,
        toggle_ppg_csv=toggle_ppg_csv,
        update_ppg_plot=update_ppg_plot,
        animation=ani_ppg,
    )
