"""Contrato da divisao de interface: sem BLE/Arduino/Tk no ambiente de testes."""
import ast
import pathlib
import unittest

GUI_DIR = pathlib.Path(__file__).resolve().parents[1] / "pitaco_bridge" / "gui"
ENTRY = pathlib.Path(__file__).resolve().parents[1] / "ble_client_mpx5010dp.py"


def names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


class GuiSplitTests(unittest.TestCase):
    def test_main_public_entry_kept(self):
        self.assertIn("run_gui", names(GUI_DIR / "main_window.py"))
        self.assertIn("from pitaco_bridge.gui import run_gui",
                      ENTRY.read_text(encoding="utf-8"))
        self.assertIn("from .main_window import run_gui",
                      (GUI_DIR / "__init__.py").read_text(encoding="utf-8"))

    def test_views_own_their_existing_callbacks(self):
        pneumo = names(GUI_DIR / "pneumo_view.py")
        cardio = names(GUI_DIR / "oxy_and_cardio_view.py")
        main = names(GUI_DIR / "main_window.py")
        for name in ("create_pneumo_view", "update_plot", "open_info_window",
                     "start_peak_calibration", "start_rate_calibration",
                     "start_timing_calibration"):
            self.assertIn(name, pneumo)
            self.assertNotIn(name, main)
        for name in ("create_oxy_and_cardio_view", "update_ppg_plot",
                     "toggle_ppg_csv"):
            self.assertIn(name, cardio)
            self.assertNotIn(name, main)
        for name in ("ble_bridge", "start_bridge", "stop_bridge",
                     "process_pitaco_line", "send_ble_command", "open_graph",
                     "close_graph", "open_ppg_graph", "close_ppg_graph"):
            self.assertIn(name, main)

    def test_views_use_shared_state_and_do_not_open_a_second_radio(self):
        pneumo = (GUI_DIR / "pneumo_view.py").read_text(encoding="utf-8")
        cardio = (GUI_DIR / "oxy_and_cardio_view.py").read_text(encoding="utf-8")
        main = (GUI_DIR / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("create_pneumo_view(sys.modules[__name__])", main)
        self.assertIn("create_oxy_and_cardio_view(sys.modules[__name__])", main)
        self.assertIn("from .oxy_and_cardio_view import create_oxy_and_cardio_view", main)
        self.assertNotIn("ser_oxi", main)
        self.assertNotIn("oxi_port_combo", main)
        self.assertNotIn("oximeter_game_port", main)
        self.assertIn("if app.is_plotting:", pneumo)
        self.assertIn("if not app.is_ppg_plotting:", cardio)
        self.assertIn("ppg_monitor.snapshot()", cardio)
        self.assertIn("ppg_metric_bpm = ctk.CTkFrame(", cardio)
        self.assertIn("ppg_metric_spo2 = ctk.CTkFrame(", cardio)
        self.assertIn("ppg_metric_bpm_mean = ctk.CTkFrame(", cardio)
        self.assertIn("ppg_metric_spo2_mean = ctk.CTkFrame(", cardio)
        self.assertIn('mean60 = snap["mean60"]', cardio)
        self.assertIn("ppg_bpm_fw_mean_value.configure(", cardio)
        self.assertIn("ppg_spo2_mean_value.configure(", cardio)
        self.assertIn('ppg_bpm_fw_value.configure(text=f"ESP32: {bpm_text}")', cardio)
        self.assertIn('ppg_bpm_py_value.configure(text=f"Python EXP.: {py_bpm}")', cardio)
        self.assertIn("ppg_spo2_value.configure(text=spo2_text)", cardio)
        self.assertIn("ppg_quality_label = ctk.CTkLabel(", cardio)
        self.assertIn("ppg_quality_label.configure(", cardio)
        self.assertIn("ax_ppg.set_xlim(xmax - 30.0, xmax + .25)", cardio)
        self.assertIn("PpgMonitor(max_points=850)", main)
        self.assertNotIn("CTkCheckBox(", cardio)
        self.assertNotIn("toggle_ppg_experiment", main + cardio)
        self.assertNotIn("BleakClient(", cardio)
        self.assertNotIn("BleakClient(", pneumo)
        self.assertNotIn("Serial(", cardio)
        self.assertNotIn("Serial(", pneumo)


if __name__ == "__main__":
    unittest.main()
