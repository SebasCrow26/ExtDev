"""Agrega `dia_semana`, `es_fin_semana` y `es_festivo` a la salida de `agregar_semana`.

Se usa en lugar de `agregar_semana` directamente cuando se necesita que la tabla
de semanas tenga las columnas de calendario que espera la línea base (clave
`planta, proceso_modelo, dia_semana`), sin romper `comun_modelos.agregar_semana`
que devuelve la forma original del contrato (`semana_inicio`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.modelos.comun_modelos import agregar_semana as _agregar_semana  # noqa: E402


def agregar_semana_con_calendario(df: pd.DataFrame) -> pd.DataFrame:
    g = _agregar_semana(df)
    g = g.copy()
    # la semana siempre arranca en lunes; dia_semana = 0 permite que la clave de la
    # línea base (planta, proceso, dia_semana) sea válida también en nivel semana
    g["dia_semana"] = 0
    g["es_fin_semana"] = 0
    g["es_festivo"] = (g["dias_festivos"] > 0).astype(int) if "dias_festivos" in g.columns else 0
    return g
