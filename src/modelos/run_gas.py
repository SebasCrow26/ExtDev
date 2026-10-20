"""run_gas.py — gas de refinación: línea base por día de la semana + energía de refinación (Joshua).

Con solo 53 días confiables (documentacion/10, documentacion/11 F1–F3), la especificación recomienda una línea base
por día de la semana con la energía de refinación como covariable, y documentar la limitación.
Este script la ajusta y la evalúa, sin pretender un modelo robusto.

Salida: documentacion/modelos/gas.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402

DOCS = RAIZ / "documentacion" / "modelos"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def metricas(y_real, y_pred):
    y_real = np.asarray(y_real, float); y_pred = np.asarray(y_pred, float)
    mae = float(np.mean(np.abs(y_real - y_pred)))
    wape = 100 * mae / float(np.sum(np.abs(y_real))) if np.sum(np.abs(y_real)) else np.nan
    ss_res = float(np.sum((y_real - y_pred) ** 2))
    ss_tot = float(np.sum((y_real - np.mean(y_real)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"mae": round(mae, 1), "wape": round(wape, 2), "r2": round(r2, 3), "n": len(y_real)}


def main():
    gas = leer_tabla("dataset_modelo_gas_dia")
    gas = gas[gas["calidad_ok"] == 1].copy().sort_values("fecha")
    gas["refinacion"] = gas["produccion_refinacion_kg"].fillna(0)

    # línea base por día de la semana
    medias = gas.groupby("dia_semana")["m3"].mean()
    pred_lb = gas["dia_semana"].map(medias).to_numpy()
    m_lb = metricas(gas["m3"], pred_lb)

    # línea base + energía de refinación como covariable (regresión simple sobre el residuo de la línea base)
    resid = gas["m3"].to_numpy() - pred_lb
    if np.std(gas["refinacion"]) > 0:
        pend, base = np.polyfit(gas["refinacion"], resid, 1)
        pred_comp = pred_lb + base + pend * gas["refinacion"].to_numpy()
        m_comp = metricas(gas["m3"], pred_comp)
    else:
        pend = base = np.nan
        m_comp = m_lb

    lineas = ["# Gas de refinación — línea base por día de la semana (Joshua)", "",
             "Según `documentacion/03_especificacion_modelos.md` y `documentacion/10_eda_fa_gas.md`: con solo **53 días confiables** "
             "no hay modelo sólido; se recomienda una línea base por día de la semana con la energía de refinación "
             "como covariable, y documentar la limitación.", "",
             f"**Datos:** `dataset_modelo_gas_dia` con `calidad_ok=1` ({len(gas)} días).", "",
             "## 1. Línea base por día de la semana", "",
             md_tabla(pd.DataFrame({"dia_semana": medias.index, "m3_medio": medias.round(0).values})), "",
             f"Métricas de la línea base: MAE {m_lb['mae']}, WAPE {m_lb['wape']}%, R² {m_lb['r2']}.", "",
             "## 2. Línea base + energía de refinación como covariable", "",
             f"- Ajuste del residuo: `residuo = {base:.1f} + {pend:.5f} × producción_refinacion_kg`.",
             f"- Métricas: MAE {m_comp['mae']}, WAPE {m_comp['wape']}%, R² {m_comp['r2']}.",
             "",
             "## 3. Limitación declarada (obligatoria en la presentación)", "",
             "- **53 días confiables** (de 60): 3 estimados y 4 con reinicio del acumulado (límite inferior).",
             "- El gas del SCADA **no concilia** con la base mensual de Clarios (no hay mes común; ver F2 de "
             "`documentacion/11_cifras_verificadas.md`): este modelo describe el SCADA, no el gas total de la planta.",
             "- La correlación diaria con la energía de refinación es **0.49** (R² 0.10): débil. No se debe "
             "presentar como un modelo predictivo fiable, sino como una primera línea base con la limitación a la vista.",
             "- El domingo concentra más gas (~1,392 m³) sin explicación conocida: pendiente de preguntar a Clarios.", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "gas.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / 'gas.md'}")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
