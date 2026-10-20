"""01_exploracion.py — Exploración de modelado (Joshua).

Recorre dataset_modelo por nivel (turno / día / semana) y proceso, y reporta:
relación kWh–producción (Pearson/Spearman), fracción de turnos sin transacciones,
consumo base estimado (regresión por mínimos cuadrados kwh = base + pendiente·producción),
efecto de fin de semana y de festivo, y el desfase de producción más correlacionado.

Salida: documentacion/modelos/01_exploracion.md (no toca data/clean).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402
from src.modelos.comun_modelos import (  # noqa: E402
    PROCESOS_RC, PROCESO_FA, agregar_dia, agregar_semana, cfg_modelos,
)


def regresion_simple(x, y):
    """kwh = base + pendiente·producción por mínimos cuadrados; devuelve (base, pendiente, r2)."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    if len(x) < 3 or np.std(x) == 0:
        return np.nan, np.nan, np.nan
    pend, base = np.polyfit(x, y, 1)
    pred = base + pend * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return round(base, 1), round(pend, 4), round(1 - ss_res / ss_tot, 4)


def corr(x, y) -> float:
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    m = ~(np.isnan(x) | np.isnan(y))
    if m.sum() < 3 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return np.nan
    return round(float(np.corrcoef(x[m], y[m])[0, 1]), 3)


def main():
    cfg = cfg_modelos()
    dm = leer_tabla("dataset_modelo")
    dm = dm[(dm["planta"] == "RC") & (dm["proceso_modelo"].isin(PROCESOS_RC))]
    fa = leer_tabla("dataset_modelo")
    fa = fa[fa["planta"] == "F&A"].rename(columns={"proceso_modelo": "proceso_modelo"})

    lineas = ["# 01 · Exploración de modelado (Joshua)", "",
             f"Datos de `dataset_modelo` (fuente: {dm.attrs.get('fuente', '?')}). "
             "RC se modela por **día y semana** (la producción se reporta por lotes); "
             "por turno la producción casi no explica la energía (ver documentacion/03).", ""]

    niveles = {
        "turno": (dm, "fecha_turno", "produccion"),
        "dia": (agregar_dia(dm), "fecha_turno", "produccion"),
        "semana": (agregar_semana(dm).rename(columns={"semana_inicio": "fecha_turno"}), "fecha_turno", "produccion"),
    }

    lineas += ["## RC — relación kWh–producción y consumo base por nivel", "",
               "| nivel | proceso | n | r | R²(ajuste) | base kWh | pendiente kWh/unid | sin transacciones % |",
               "|---|---|---|---|---|---|---|---|"]
    for nivel, (tabla, colf, colp) in niveles.items():
        for proc in PROCESOS_RC:
            t = tabla[tabla["proceso_modelo"] == proc]
            ok = t[t["calidad_ok"] == 1]
            if ok.empty:
                continue
            r = corr(ok[colp], ok["kwh"])
            base, pend, r2 = regresion_simple(ok[colp], ok["kwh"])
            sin_tx = 100 * (ok["n_transacciones"] == 0).mean()
            lineas.append(f"| {nivel} | {proc} | {len(ok)} | {r} | {r2} | {base} | {pend} | {sin_tx:.0f} |")

    # Efecto fin de semana y festivo (solo turnos con calidad_ok)
    lineas += ["", "## RC — efecto de calendario (kWh medio por turno, calidad_ok)", "",
               "| proceso | día laboral | fin de semana | festivo laborable | Δ fin de semana % |",
               "|---|---|---|---|---|"]
    ok = dm[dm["calidad_ok"] == 1]
    for proc in PROCESOS_RC:
        t = ok[ok["proceso_modelo"] == proc]
        lab = t[(t["es_fin_semana"] == 0) & (t["es_festivo"] == 0)]["kwh"].mean()
        fin = t[t["es_fin_semana"] == 1]["kwh"].mean()
        fest = t[(t["es_fin_semana"] == 0) & (t["es_festivo"] == 1)]["kwh"].mean()
        delta = 100 * (fin - lab) / lab if lab else np.nan
        lineas.append(f"| {proc} | {lab:.0f} | {fin:.0f} | {fest:.0f} | {delta:+.0f} |")

    # Desfase de producción (por día, RC); desplazar la producción es exploratorio,
    # el modelo final usa solo rezagos de producción (causales), no de energía.
    dia = agregar_dia(dm)
    lineas += ["", "## RC — desfase producción→energía (correlación por día; exploratorio)", "",
               "| proceso | prod(t) | prod(t−1) | prod(t−2) | prod(t+1) |", "|---|---|---|---|---|"]
    for proc in PROCESOS_RC:
        t = dia[dia["proceso_modelo"] == proc].sort_values("fecha_turno")
        vals = [corr(t["produccion"].shift(lag), t["kwh"]) for lag in (0, 1, 2, -1)]
        lineas.append(f"| {proc} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")

    # F&A (turno): encendido/apagado
    lineas += ["", "## F&A formación — encendido/apagado vs producción", "",
               f"Turnos con `calidad_ok`: {(fa['calidad_ok'] == 1).sum()} de {len(fa)}. "
               f"Correlación kWh–unidades por turno: {corr(fa['produccion'], fa['kwh'])}. "
               "La especificación (documentacion/03) indica modelar primero cuántos turnos están encendidos "
               "(arranque domingo 22:00, cierre sábado 14:00) y luego la parte variable.", ""]

    out = RAIZ / "documentacion" / "modelos"
    out.mkdir(parents=True, exist_ok=True)
    (out / "01_exploracion.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {out / '01_exploracion.md'} ({len(lineas)} líneas)")
    print("\n".join(lineas[:40]))


if __name__ == "__main__":
    main()
