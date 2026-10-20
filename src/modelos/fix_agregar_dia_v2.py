"""Versión corregida de `agregar_dia_con_calendario`: asegura columnas de calendario
con un merge (evita desajuste de índices cuando `agregar_dia` filtra días incompletos).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.modelos.comun_modelos import agregar_dia as _agregar_dia  # noqa: E402


def agregar_dia_con_calendario(df: pd.DataFrame) -> pd.DataFrame:
    g = _agregar_dia(df).copy()
    g["dia_semana"] = g["fecha_turno"].dt.dayofweek
    g["es_fin_semana"] = (g["dia_semana"] >= 5).astype(int)
    if "es_festivo" in df.columns:
        fest = df.groupby(["fecha_turno", "planta", "proceso_modelo"])["es_festivo"].max()
        g = g.merge(fest.rename("es_festivo").reset_index(), on=["fecha_turno", "planta", "proceso_modelo"], how="left")
    else:
        g["es_festivo"] = 0
    return g
