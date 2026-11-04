"""Pneumógrafo: janela, aferições, relatório e desenho de fluxo/pressão.

Conteúdo movido de gui.py. Continua usando o estado e a conexão únicos
de main_window, sem duplicar filtros, calibrações ou comandos.
"""
import math
import os
import threading
import time
from types import SimpleNamespace
from tkinter import messagebox

import customtkinter as ctk
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def create_pneumo_view(app):
    """Monta a janela existente e devolve seus widgets/callbacks ao main."""
    root = app.root
    close_graph = app.close_graph
    log = app.log
    plot_data_flow = app.plot_data_flow
    flow_to_pressure = app.flow_to_pressure
    update_active_profile_metrics = app.update_active_profile_metrics

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

    profile_badge_label = ctk.CTkLabel(header_top_row, text=f"👤 Perfil: {app.active_profile_name}", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0")
    profile_badge_label.pack(side="left", padx=(0, 10))

    current_val_label = ctk.CTkLabel(header_top_row, text="Fluxo: 0.00 L/min", font=("Segoe UI", 13, "bold"), text_color="#ffffff")
    current_val_label.pack(side="left", padx=(0, 10))

    max_val_label = ctk.CTkLabel(header_top_row, text=f"Máx (Exp): +{app.persistent_max_flow:.2f} L/min", font=("Segoe UI", 12, "bold"), text_color="#28a745")
    max_val_label.pack(side="left", padx=(0, 10))

    min_val_label = ctk.CTkLabel(header_top_row, text=f"Mín (Insp): {app.persistent_min_flow:.2f} L/min", font=("Segoe UI", 12, "bold"), text_color="#17a2b8")
    min_val_label.pack(side="left", padx=(0, 10))

    # Linha 2 do Header (Métricas em formato de texto)
    header_bottom_row = ctk.CTkFrame(popup_header_frame, fg_color="transparent")
    header_bottom_row.pack(fill="x", padx=8, pady=(2, 6))

    rate_val_label = ctk.CTkLabel(header_bottom_row, text=f"Taxa: {app.persistent_resp_rate:.0f} rpm" if app.persistent_resp_rate > 0 else "Taxa: -- rpm", font=("Segoe UI", 11, "bold"), text_color="#ffc107")
    rate_val_label.pack(side="left", padx=(0, 15))

    init_timing_text = f"Ins: {app.persistent_t_ins:.1f}s | Exp: {app.persistent_t_exp:.1f}s | I:E {app.persistent_ie_ratio}" if (app.persistent_t_ins > 0 and app.persistent_t_exp > 0) else "Tempos Ins/Exp: --"
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

        sub_lbl = ctk.CTkLabel(main_f, text=f"Paciente / Perfil: {app.active_profile_name}  |  Última Aferição: {app.persistent_last_updated}", font=("Segoe UI", 11), text_color="#aaaaaa")
        sub_lbl.pack(anchor="w", pady=(0, 10))

        # Card 1: Picos de Fluxo
        c1 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
        c1.pack(fill="x", pady=4, padx=2)
        ctk.CTkLabel(c1, text="Picos de Fluxo Máximo e Mínimo", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
        ctk.CTkLabel(c1, text=f"• Pico Expiratório Máximo (PEF):  +{app.persistent_max_flow:.2f} L/min", font=("Segoe UI", 11), text_color="#28a745").pack(anchor="w", padx=12, pady=1)
        ctk.CTkLabel(c1, text=f"• Pico Inspiratório Mínimo (PIF):  {app.persistent_min_flow:.2f} L/min", font=("Segoe UI", 11), text_color="#17a2b8").pack(anchor="w", padx=12, pady=(1, 6))

        # Card 2: Taxa Respiratória
        c2 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
        c2.pack(fill="x", pady=4, padx=2)
        ctk.CTkLabel(c2, text="Taxa Respiratória (Freq. em Repouso)", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
        rate_str = f"{app.persistent_resp_rate:.0f} rpm (incursões/min)" if app.persistent_resp_rate > 0 else "Não aferida"
        ctk.CTkLabel(c2, text=f"• Taxa Medida (1 min):  {rate_str}", font=("Segoe UI", 11), text_color="#ffc107").pack(anchor="w", padx=12, pady=1)
        ctk.CTkLabel(c2, text="  ↳ Faixa de referência em repouso: 12 a 20 rpm", font=("Segoe UI", 10), text_color="#888888").pack(anchor="w", padx=12, pady=(1, 6))

        # Card 3: Cinética e Tempos de Ciclo
        c3 = ctk.CTkFrame(main_f, fg_color="#1f1f1f", corner_radius=6)
        c3.pack(fill="x", pady=4, padx=2)
        ctk.CTkLabel(c3, text="Cinética Respiratória (Tempos Ins / Exp)", font=("Segoe UI", 12, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=12, pady=(6, 2))
        if app.persistent_t_ins > 0 and app.persistent_t_exp > 0:
            ctk.CTkLabel(c3, text=f"• Tempo Inspiratório Médio (T.ins):  {app.persistent_t_ins:.2f} s", font=("Segoe UI", 11), text_color="#ffffff").pack(anchor="w", padx=12, pady=1)
            ctk.CTkLabel(c3, text=f"• Tempo Expiratório Médio (T.exp):  {app.persistent_t_exp:.2f} s", font=("Segoe UI", 11), text_color="#ffffff").pack(anchor="w", padx=12, pady=1)
            ctk.CTkLabel(c3, text=f"• Relação I:E:  {app.persistent_ie_ratio}", font=("Segoe UI", 11, "bold"), text_color="#28a745").pack(anchor="w", padx=12, pady=1)
        else:
            ctk.CTkLabel(c3, text="• Tempos ainda não aferidos.", font=("Segoe UI", 11), text_color="#888888").pack(anchor="w", padx=12, pady=1)
        ctk.CTkLabel(c3, text="  ↳ Relação fisiológica de referência: 1:1.5 a 1:2.0", font=("Segoe UI", 10), text_color="#888888").pack(anchor="w", padx=12, pady=(1, 6))

        btn_close = ctk.CTkButton(main_f, text="Fechar", width=100, height=30, command=info_win.destroy)
        btn_close.pack(pady=(10, 0))

    def start_peak_calibration():
        if not app.running:
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
        if not app.running:
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
        if not app.running:
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


    show_pressure_var = ctk.BooleanVar(value=True)

    fig, ax1 = plt.subplots(figsize=(6, 4), dpi=100)
    fig.patch.set_facecolor('#2b2b2b') 
    ax1.set_facecolor('#2b2b2b')

    ax1.set_ylabel('Fluxo (L/min)', color='#ffffff')
    ax1.tick_params(axis='x', colors='white')
    ax1.tick_params(axis='y', colors='#ffffff')

    ax1.minorticks_on()
    ax1.grid(True, which='major', linestyle='-', linewidth=0.8, color='#555555')
    ax1.grid(True, which='minor', linestyle=':', linewidth=0.5, color='#444444')

    line_flow, = ax1.plot(plot_data_flow, color='#ffffff', label='Fluxo', linewidth=2)
    hline_max = ax1.axhline(y=app.persistent_max_flow, color='#28a745', linestyle='--', linewidth=1.5, alpha=0.85, label='Máx')
    hline_min = ax1.axhline(y=app.persistent_min_flow, color='#17a2b8', linestyle='--', linewidth=1.5, alpha=0.85, label='Mín')

    ax2 = ax1.twinx()
    ax2.set_ylabel('Pressão (Pa)', color='#ffffff')
    ax2.tick_params(axis='y', colors='#ffffff')
    ax2.yaxis.set_visible(False)

    canvas = FigureCanvasTkAgg(fig, master=plot_window)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_plot(frame):
        if app.is_plotting:
            latest_flow = plot_data_flow[-1] if len(plot_data_flow) > 0 else 0.0
            current_val_label.configure(text=f"Fluxo: {latest_flow:.2f} L/min")

            line_flow.set_ydata(plot_data_flow)
            hline_max.set_ydata([app.persistent_max_flow, app.persistent_max_flow])
            hline_min.set_ydata([app.persistent_min_flow, app.persistent_min_flow])

            all_vals = list(plot_data_flow) + [app.persistent_max_flow, app.persistent_min_flow]
            f_min, f_max = min(all_vals), max(all_vals)
            f_pad = max(5.0, (f_max - f_min) * 0.1) 
            f_lower, f_upper = f_min - f_pad, f_max + f_pad
            ax1.set_ylim(f_lower, f_upper)
            
            if show_pressure_var.get():
                ax2.yaxis.set_visible(True)
                ax2.set_ylim(flow_to_pressure(f_lower), flow_to_pressure(f_upper))
            else:
                ax2.yaxis.set_visible(False) 
            canvas.draw()
        return line_flow,

    # O painel pneumo continua com o grafico e processamento respiratorio original.
    ani = animation.FuncAnimation(fig, update_plot, interval=150, blit=False,
                                  cache_frame_data=False)


    return SimpleNamespace(
        window=plot_window,
        profile_badge_label=profile_badge_label,
        current_val_label=current_val_label,
        max_val_label=max_val_label,
        min_val_label=min_val_label,
        rate_val_label=rate_val_label,
        timing_val_label=timing_val_label,
        header_top_row=header_top_row,
        open_info_window=open_info_window,
        start_peak_calibration=start_peak_calibration,
        start_rate_calibration=start_rate_calibration,
        start_timing_calibration=start_timing_calibration,
        on_aferir_selected=on_aferir_selected,
        update_plot=update_plot,
        animation=ani,
    )
