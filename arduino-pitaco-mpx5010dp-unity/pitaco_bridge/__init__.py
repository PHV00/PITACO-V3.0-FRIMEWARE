"""Middleware PITACO 2.4: transporte, processamento e interface.

A dependencia deve fluir de gui -> transport/monitor -> protocol/experimental.
Nunca importar gui em modulos de dados: Tk, Bleak e portas reais nao sao
necessarios para os testes unitarios.
"""
