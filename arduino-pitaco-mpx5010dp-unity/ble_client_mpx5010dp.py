"""Entrada estavel do middleware PITACO 2.4 (USB/BLE + Pneumo/PPG).

Interface e logica foram movidas para pitaco_bridge/.
O comando historico permanece: python ble_client_mpx5010dp.py
"""

from pitaco_bridge.gui import run_gui


if __name__ == "__main__":
    run_gui()
