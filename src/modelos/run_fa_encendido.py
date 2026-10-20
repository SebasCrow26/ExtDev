"""run_fa_encendido.py — F&A: encendido/apagado + parte variable, con validación por ventanas móviles (Joshua).

Según `documentacion/03_especificacion_modelos.md` y `documentacion/10_eda_fa_gas.md`, el consumo de formación depende
sobre todo de **cuántos turnos están encendidos** (arranque domingo 22:00, cierre sábado 14:00),
no de las unidades producidas dentro de la operación (R² 0.15 por turno en operación).

Este script:
1. Modelo 1 (encendido): clasifica cada turno como encendido/apagado según el patrón semanal
   documentado (domingo T3 → sábado T1) y lo evalúa contra `dataset_modelo` de F&A.
2. Modelo 2 (parte variable): dentro de los turnos encendidos, regresión simple kWh ~ unidades.
3. Validación por ventanas móviles (solo 3 meses de datos, ver limitación de la especificación).

Salida: documentacion/modelos/fa_encendido.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402
from src.modelos.comun_modelos import PROCESO_FA, metricas  # noqa: E402
from src.modelos.h10 import excluir_h10  # noqa: E402

DOCS = RAIZ / "documentacion" / "modelos"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def encendido_programado(dia_semana: int, turno: int) -> int:
    """Patrón documentado en documentacion/10: arranque domingo T3, cierre sábado T1."""
    if dia_semana == 6 and turno == 3:  # domingo T3 (arranque)
        return 1
    if dia_semana == 6:  # domingo T1 y T2: apagado
        return 0
    if dia_semana == 5 and turno == 1:  # sábado T1: todavía encendido
        return 1
    if dia_semana == 5:  # sábado T2 y T3: apagado
        return 0
    return 1  # lunes a viernes: encendido


def main():
    dm = leer_tabla("dataset_modelo")
    fa = dm[dm["proceso_modelo"] == PROCESO_FA].copy()
    fa = excluir_h10(fa)  # decisión H10: excluir la semana del 13 jul 2026
    fa = fa[fa["calidad_ok"] == 1].sort_values("fecha_turno")

    fa["encendido_prog"] = [encendido_programado(d, t) for d, t in zip(fa["dia_semana"], fa["turno"])]
    fa["encendido_real"] = (fa["kwh"] > 0.5 * fa["kwh"].median()).astype(int)

    acierto = (fa["encendido_prog"] == fa["encendido_real"]).mean()

    # parte variable: solo turnos encendidos
    enc = fa[fa["encendido_real"] == 1]
    X = enc["produccion"].to_numpy()
    y = enc["kwh"].to_numpy()
    if len(X) > 3 and np.std(X) > 0:
        pend, base = np.polyfit(X, y, 1)
        pred = base + pend * X
        m_var = metricas(y, pred)
    else:
        pend = base = np.nan
        m_var = {"mae": np.nan, "wape": np.nan, "r2": np.nan, "n": len(X)}

    # validación por ventanas móviles (3-fold temporal sobre los ~3 meses)
    folds = np.array_split(np.arange(len(fa)), 3)
    fold_rows = []
    for i in range(len(folds) - 1):
        tr = fa.iloc[np.concatenate(folds[: i + 1])]
        te = fa.iloc[folds[i + 1]]
        tr_enc = tr[tr["encendido_real"] == 1]
        if len(tr_enc) > 3 and np.std(tr_enc["produccion"]) > 0:
            p, b = np.polyfit(tr_enc["produccion"], tr_enc["kwh"], 1)
            pred = b + p * te["produccion"].to_numpy()
            pred = np.clip(pred, 0, None)
            me = metricas(te["kwh"], pred)
        else:
            me = {"mae": np.nan, "wape": np.nan, "r2": np.nan, "n": len(te)}
        fold_rows.append({"fold": f"{i+1}->{i+2}", "n_pru": me["n"], "MAE": me["mae"], "WAPE": me["wape"], "R2": me["r2"]})

    lineas = ["# F&A formación — encendido/apagado y parte variable (Joshua)", "",
             "La especificación (`documentacion/03`) y el EDA (`documentacion/10`) indican que el consumo de formación depende "
             "sobre todo de **cuántos turnos están encendidos** (arranque domingo 22:00, cierre sábado 14:00), "
             "no de las unidades dentro de la operación (R² 0.15 por turno en operación).", "",
             f"**Datos:** `dataset_modelo` de F&A, solo `calidad_ok=1`, **con la semana del 13 jul 2026 excluida "
             f"(decisión H10)**: {len(fa)} turnos.", "",
             "## 1. Modelo de encendido (patrón semanal documentado)", "",
             f"- Regla: encendido de domingo T3 a sábado T1 (inclusive); apagado el resto del fin de semana.",
             f"- Acierto contra el consumo observado (`kwh > 0.5 × mediana`): **{acierto:.1%}**.",
             "",
             "## 2. Parte variable (solo turnos encendidos)", "",
             f"- Regresión simple `kwh = {base:.0f} + {pend:.4f} × unidades` (n = {m_var['n']}).",
             f"- Métricas: MAE {m_var['mae']}, WAPE {m_var['wape']}%, R² {m_var['r2']}.",
             "- **Lectura:** confirma lo de la especificación: dentro de operación el consumo casi no depende "
             "de las unidades (R² bajo). El valor está en el modelo de encendido, no en la pendiente.",
             "",
             "## 3. Validación por ventanas móviles (3-fold temporal)", "",
             md_tabla(pd.DataFrame(fold_rows)), "",
             "**Limitación declarada:** solo 3 meses de datos (jul–sep 2026) y 12 turnos de formación dejaron "
             "de ser válidos por el congelamiento del RECTIFICADOR_2 (documentacion/11 B5). La validación por ventanas "
             "móviles es la que permite la especificación dada la escasez de historia; no sustituye una "
             "validación con más datos.", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "fa_encendido.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / 'fa_encendido.md'}")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
