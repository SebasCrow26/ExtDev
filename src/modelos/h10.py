"""h10.py — decisión H10 (Joshua): excluir la semana del 13 de julio de 2026 de F&A del modelado.

Sebastián documentó (documentacion/04, documentacion/11 B5, documentacion/14 H10) que esa semana queda con cobertura 0.80
tras el congelamiento del RECTIFICADOR_2 y que su valor reescalado (`kwh = kwh_observado / cobertura`)
probablemente sobrestima. Decisión del equipo (Joshua, 15 oct): **excluir la semana del modelado**
y de las métricas, no usar `kwh_observado` ni el valor reescalado.

Este módulo expone `SEMANA_H10` y `excluir_h10(df, col_fecha)` para que los scripts de Modelos
la filtren de forma explícita y documentada.
"""
from __future__ import annotations

import pandas as pd

# Semana (lunes a domingo) que contiene el 13 de julio de 2026
SEMANA_H10 = ("2026-07-13", "2026-07-19")


def excluir_h10(df: pd.DataFrame, col_fecha: str = "fecha_turno") -> pd.DataFrame:
    """Excluye la semana del 13 de julio de 2026 de F&A (hallazgo H10 de `documentacion/14_informe_calidad_v1.md`).

    Solo aplica a F&A (`planta == "F&A"` o `proceso_modelo == "formacion"`); RC no se ve afectado.
    """
    inicio, fin = pd.Timestamp(SEMANA_H10[0]), pd.Timestamp(SEMANA_H10[1])
    f = pd.to_datetime(df[col_fecha])
    es_fa = df["planta"].eq("F&A") if "planta" in df.columns else df.get("proceso_modelo", pd.Series(dtype=str)).eq("formacion")
    fuera = es_fa & f.between(inicio, fin)
    return df.loc[~fuera].copy()
