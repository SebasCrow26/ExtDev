"""Punto de entrada alternativo: ejecuta la línea base con `dia_semana` incluido en nivel semana.

Este archivo evita el conflicto de sobrescritura de `02_linea_base.py` mientras se integran los cambios.
Ejecuta exactamente la misma lógica que `02_linea_base.py`, pero usando
`fix_agregar_semana.agregar_semana_con_calendario` en lugar de `comun_modelos.agregar_semana`.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402
from src.modelos.comun_modelos import (  # noqa: E402
    PROCESOS_RC, PROCESO_FA, agregar_dia, metricas, split_temporal,
)
from src.modelos.fix_agregar_semana import agregar_semana_con_calendario  # noqa: E402

INTERIM = RAIZ / "data" / "interim"
DOCS = RAIZ / "documentacion" / "modelos"


def ajustar_linea_base(ent: pd.DataFrame, nivel: str):
    claves = ["planta", "proceso_modelo", "turno", "dia_semana"] if nivel == "turno" else ["planta", "proceso_modelo", "dia_semana"]
    medias = ent.groupby(claves)["kwh"].mean()
    general = ent.groupby(["planta", "proceso_modelo"])["kwh"].mean()
    return {"nivel": nivel, "claves": claves, "medias": medias, "general": general}


def predecir_linea_base(modelo, tab: pd.DataFrame) -> pd.Series:
    claves, medias, general = modelo["claves"], modelo["medias"], modelo["general"]
    idx = pd.MultiIndex.from_frame(tab[claves])
    pred = medias.reindex(idx).to_numpy()
    falta = pd.isna(pred)
    if falta.any():
        gen = general.reindex(pd.MultiIndex.from_frame(tab.loc[falta, ["planta", "proceso_modelo"]])).to_numpy()
        pred[falta] = gen
    return pd.Series(pred, index=tab.index)


def _evaluar(nivel, tab_ent, tab_pru):
    m = ajustar_linea_base(tab_ent, nivel)
    return m, metricas(tab_ent["kwh"], predecir_linea_base(m, tab_ent)), metricas(tab_pru["kwh"], predecir_linea_base(m, tab_pru))


def main():
    dm = leer_tabla("dataset_modelo")
    dm = dm[dm["proceso_modelo"].isin(PROCESOS_RC + [PROCESO_FA])].copy()
    dm.loc[dm["proceso_modelo"] == PROCESO_FA, "planta"] = "F&A"

    lineas = ["# 02 · Línea base (promedio proceso × turno × día de la semana)", "",
             "La referencia que cualquier modelo debe superar en la **prueba (jul–sep 2026)**. "
             "Split temporal según `config/config.yaml`, nunca aleatorio.", ""]
    modelos, resumen = {}, []

    ent, pru = split_temporal(dm[dm["calidad_ok"] == 1], "fecha_turno")
    for proc in PROCESOS_RC + [PROCESO_FA]:
        e, p = ent[ent["proceso_modelo"] == proc], pru[pru["proceso_modelo"] == proc]
        if e.empty or p.empty:
            continue
        m, me, mp = _evaluar("turno", e, p)
        modelos[f"turno|{proc}"] = m
        resumen.append(("turno", proc, me, mp))

    dia = agregar_dia(dm); dia = dia[dia["calidad_ok"] == 1]
    ent_d, pru_d = split_temporal(dia, "fecha_turno")
    for proc in PROCESOS_RC + [PROCESO_FA]:
        e, p = ent_d[ent_d["proceso_modelo"] == proc], pru_d[pru_d["proceso_modelo"] == proc]
        if e.empty or p.empty:
            continue
        m, me, mp = _evaluar("dia", e, p)
        modelos[f"dia|{proc}"] = m
        resumen.append(("dia", proc, me, mp))

    sem = agregar_semana_con_calendario(dm); sem = sem[sem["calidad_ok"] == 1].rename(columns={"semana_inicio": "fecha_turno"})
    ent_s, pru_s = split_temporal(sem, "fecha_turno")
    for proc in PROCESOS_RC + [PROCESO_FA]:
        e, p = ent_s[ent_s["proceso_modelo"] == proc], pru_s[pru_s["proceso_modelo"] == proc]
        if e.empty or p.empty:
            continue
        m, me, mp = _evaluar("semana", e, p)
        modelos[f"semana|{proc}"] = m
        resumen.append(("semana", proc, me, mp))

    lineas += ["## Métricas de la línea base (MAE kWh, WAPE %, R² clásico vs media real)", "",
               "| nivel | proceso | n_ent | MAE_ent | WAPE_ent | R²_ent | n_pru | MAE_pru | WAPE_pru | R²_pru |",
               "|---|---|---|---|---|---|---|---|---|---|"]
    for nivel, proc, me, mp in resumen:
        lineas.append(f"| {nivel} | {proc} | {me['n']} | {me['mae']} | {me['wape']} | {me['r2']} | "
                      f"{mp['n']} | {mp['mae']} | {mp['wape']} | {mp['r2']} |")
    lineas += ["", "La línea base **no ve la producción**, solo el calendario (turno y día de la semana). "
               "El modelo de regresión de `run_modelo_v6.py` debe superar estos WAPE/R² en la prueba.", ""]

    INTERIM.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(INTERIM / "linea_base.pkl", "wb") as f:
        pickle.dump({"ajustes": modelos, "metricas": resumen}, f)
    (DOCS / "02_linea_base.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escritos {DOCS / '02_linea_base.md'} y {INTERIM / 'linea_base.pkl'}")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
