"""PITACO Bridge — pacote das janelas da aplicação.

O main histórico importa run_gui daqui; responsabilidades:
main_window (coordenação), pneumo_view e oxy_and_cardio_view (apresentação).
"""
from .main_window import run_gui

__all__ = ["run_gui"]
