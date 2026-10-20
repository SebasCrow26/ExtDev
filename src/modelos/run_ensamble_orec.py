"""run_ensamble_orec.py — pronóstico mensual de Ensamble y OREC contra el presupuesto (Joshua).

Ensamble y OREC solo tienen serie **mensual** en `base_mensual_plantas.csv` (~80 meses):
- sirven para **pronóstico mensual** y para **comparar contra el presupuesto** de Clarios
  (`kwh_por_eq_presupuesto`, ver `metas_clarios.csv`), como indica `documentacion/03_especificacion_modelos.md`.
- No hay SCADA ni producción por turno para estas plantas: no aplica el modelo de consumo esperado.

Este script:
1. Calcula el cumplimiento real vs presupuesto por mes (kWh por equivalente).
2. Pronóstico mensual simple (media móvil de los últimos 3 meses) de `kwh` y `kwh_por_eq`, marcado
   como **ilustrativo**: sin plan de producción FY27 de Clarios (G5 de `documentacion/11_cifras_verificadas.md`).

Salida: documentacion/modelos/ensamble_orec.md y data/clean/pronostico_mensual_plantas.csv
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
CLEAN = RAIZ / "data" / "clean"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def main():
    bm = leer_tabla("base_mensual_plantas")
    bm["mes"] = pd.to_datetime(bm["mes"])
    bm = bm.sort_values(["planta", "mes"])

    metas = leer_tabla("metas_clarios")
    meta_ensamble = float(metas.loc[metas["planta"] == "Ensamble", "kwh_por_eq_meta"].iloc[0])
    meta_orec = float(metas.loc[metas["planta"] == "OREC", "kwh_por_eq_meta"].iloc[0])

    filas = []
    pronosticos = []
    for planta, meta in (("Ensamble", meta_ensamble), ("OREC", meta_orec)):
        tab = bm[bm["planta"] == planta].copy()
        if tab.empty:
            continue
        # cumplimiento del último año fiscal (oct 2025 – sep 2026) o lo que haya
        reciente = tab[tab["mes"] >= "2025-10-01"]
        for _, r in reciente.iterrows():
            if pd.isna(r["kwh_por_eq"]) or pd.isna(r["kwh_por_eq_presupuesto"]):
                continue
            filas.append({"planta": planta, "mes": r["mes"].date(),
                          "kwh": round(r["kwh"], 0) if not pd.isna(r["kwh"]) else "",
                          "produccion_eq": round(r["produccion_equivalente"], 0) if not pd.isna(r["produccion_equivalente"]) else "",
                          "kwh_por_eq": round(r["kwh_por_eq"], 3),
                          "presupuesto_kwh_por_eq": round(r["kwh_por_eq_presupuesto"], 3),
                          "cumple": "Sí" if r["kwh_por_eq"] <= meta else "No"})
        # pronóstico mensual: media móvil 3 meses de kwh y kwh_por_eq (ilustrativo, sin plan FY27)
        ult3 = tab.tail(3)
        kwh_pron = float(ult3["kwh"].mean())
        kpeq_pron = float(ult3["kwh_por_eq"].mean())
        pronosticos.append({"planta": planta, "mes_pronosticado": (tab["mes"].max() + pd.offsets.MonthBegin(1)).date(),
                            "kwh_pronosticado": round(kwh_pron, 0),
                            "kwh_por_eq_pronosticado": round(kpeq_pron, 3),
                            "presupuesto_kwh_por_eq": round(meta, 3),
                            "cumple_pronostico": "Sí" if kpeq_pron <= meta else "No"})

    cumpl = pd.DataFrame(filas)
    pron = pd.DataFrame(pronosticos)
    pron.to_csv(CLEAN / "pronostico_mensual_plantas.csv", index=False)

    pct_cump = {}
    for planta in ("Ensamble", "OREC"):
        sub = cumpl[cumpl["planta"] == planta]
        if not sub.empty:
            pct_cump[planta] = (sub["cumple"] == "Sí").mean() * 100

    lineas = ["# Ensamble y OREC — pronóstico mensual vs presupuesto (Joshua)", "",
             "Estas plantas solo tienen serie **mensual** en `base_mensual_plantas.csv` (~80 meses). "
             "No hay SCADA ni producción por turno: el modelo de consumo esperado no aplica. "
             "Sirven para **pronóstico mensual** y para **comparar contra el presupuesto** de Clarios.", "",
             "## 1. Cumplimiento real vs presupuesto (oct 2025 en adelante, o lo disponible)", "",
             md_tabla(cumpl) if not cumpl.empty else "_sin datos_", "",
             f"**% de meses que cumplen el presupuesto:** " + ", ".join(f"{k}: {v:.0f}%" for k, v in pct_cump.items()),
             "",
             "## 2. Pronóstico mensual (media móvil 3 meses, ilustrativo)", "",
             md_tabla(pron) if not pron.empty else "_sin datos_", "",
             "## 3. Limitación declarada (obligatoria en la presentación)", "",
             "- **Sin plan de producción FY27** de Clarios (G5 de `documentacion/11_cifras_verificadas.md`): "
             "el pronóstico es ilustrativo, **no un presupuesto oficial**.",
             "- Los presupuestos de Clarios (`metas_clarios.csv`) son por **planta y mes** "
             f"(Ensamble {meta_ensamble}, OREC {meta_orec} kWh/EQ), no por turno; la base trae además presupuestos por línea o proceso (G6 de `documentacion/11_cifras_verificadas.md`), que no están en `metas_clarios.csv`.",
             "- La serie mensual de OREC tiene errores de fecha conocidos (todos los diciembres con un año de más, "
             "corregidos por secuencia en `base_mensual_plantas.csv`, ver `documentacion/10_eda_fa_gas.md`).",
             "- No hay consumo por proceso: no se puede aplicar el modelo de consumo esperado ni detectar "
             "anomalías por turno en estas plantas.", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "ensamble_orec.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / 'ensamble_orec.md'} y {CLEAN / 'pronostico_mensual_plantas.csv'}")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
