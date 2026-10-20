"""Paso 8 (Datos): series mensuales de todas las plantas desde la base de Clarios (Base de datos.xlsx).

Sirve para cubrir las plantas sin SCADA horario (Ensamble y OREC), para el indicador de Clarios (kWh por equivalente),
para la tarifa del kWh y para los presupuestos (metas) que Clarios ya definió.

Uso (desde la raíz del repositorio):  python src/datos/08_base_mensual.py
Salidas en data/clean: base_mensual_plantas, base_mensual_gas_rc, tarifa_kwh_mensual, metas_clarios

Corrección: en la hoja de OREC, diciembre de 2025 aparece con año 2026. Las fechas se reconstruyen por secuencia.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.datos.energia_comun import MESES  # noqa: E402

RAW = RAIZ / "data" / "raw"
CLEAN = RAIZ / "data" / "clean"

RENOMBRE = {"KWH": "kwh", "Produccion (Equivalente)": "produccion_equivalente", "KWH/Equ (Reales)": "kwh_por_eq",
            "KWH/Equ (Presupuesto)": "kwh_por_eq_presupuesto", "Costo por KWH": "costo_kwh_cop", "Costo total KWH": "costo_total_cop",
            "(m3)": "m3", "m3 /Equ (Reales)": "m3_por_eq", "m3 /Equ (presupuesto)": "m3_por_eq_presupuesto", "Costo m3": "costo_m3_cop",
            "Total Costo m3": "costo_total_cop"}


def leer_hoja(hoja, proceso):
    d = pd.read_excel(RAW / "Base de datos.xlsx", sheet_name=hoja, header=1, engine="calamine")
    d.columns = [" ".join(str(c).split()) for c in d.columns]
    d = d[d["Año"].notna() & (d["Proceso"].astype(str).str.strip() == proceso)].copy()
    d = d.rename(columns=RENOMBRE)
    # reconstruir la fecha por secuencia (las hojas son mensuales y consecutivas)
    anios, meses = d["Año"].astype(int).tolist(), [MESES[str(m).strip().lower()[:3]] for m in d["Mes"]]
    fechas, avisos = [], []
    for i, (a, m) in enumerate(zip(anios, meses)):
        if i == 0:
            f = pd.Period(year=a, month=m, freq="M")
        else:
            esperado = fechas[-1] + 1
            f = esperado if m == esperado.month else pd.Period(year=a, month=m, freq="M")
            if f != pd.Period(year=a, month=m, freq="M"):
                avisos.append(f"{hoja}: fila {i + 1} decía {a}-{m:02d}, se usa {f}")
        fechas.append(f)
    d["mes"] = [f.to_timestamp().date() for f in fechas]
    saltos = [f"{fechas[i - 1]} -> {fechas[i]}" for i in range(1, len(fechas)) if fechas[i] != fechas[i - 1] + 1]
    return d, avisos, saltos


def main():
    partes, avisos_tot = [], []
    for hoja, planta in [("Ensamble", "Ensamble"), ("OREC", "OREC"), ("F&A", "F&A"), ("RC Energia", "RC")]:
        d, avisos, saltos = leer_hoja(hoja, "RC" if planta == "RC" else planta)
        avisos_tot += avisos + [f"{hoja}: salto en la secuencia {s}" for s in saltos]
        cols = ["mes", "kwh", "produccion_equivalente", "kwh_por_eq", "kwh_por_eq_presupuesto", "costo_kwh_cop", "costo_total_cop"]
        d = d[[c for c in cols if c in d.columns]].copy()
        d.insert(0, "planta", planta)
        partes.append(d)
    base = pd.concat(partes, ignore_index=True)
    for c in ["costo_kwh_cop", "kwh_por_eq_presupuesto", "costo_total_cop"]:
        base[c] = pd.to_numeric(base[c], errors="coerce")
    base.loc[base["costo_total_cop"] == 0, "costo_total_cop"] = np.nan
    base.round(2).to_csv(CLEAN / "base_mensual_plantas.csv", index=False)

    gas, av, sal = leer_hoja("RC GAS", "RC")
    avisos_tot += av + [f"RC GAS: salto en la secuencia {s}" for s in sal]
    gas = gas[["mes", "m3", "produccion_equivalente", "m3_por_eq", "costo_m3_cop", "costo_total_cop"]].copy()
    gas["costo_m3_cop"] = pd.to_numeric(gas["costo_m3_cop"], errors="coerce")
    gas.loc[gas["costo_total_cop"] == 0, "costo_total_cop"] = np.nan
    gas.round(2).to_csv(CLEAN / "base_mensual_gas_rc.csv", index=False)

    tar = base.dropna(subset=["costo_kwh_cop"]).groupby("mes")["costo_kwh_cop"].agg(["min", "max", "count"]).reset_index()
    tarifa = tar[["mes"]].assign(costo_kwh_cop=base.dropna(subset=["costo_kwh_cop"]).groupby("mes")["costo_kwh_cop"].mean().round(2).to_numpy())
    tarifa.to_csv(CLEAN / "tarifa_kwh_mensual.csv", index=False)

    pres = base.dropna(subset=["kwh_por_eq_presupuesto"]).copy()
    pres["grupo"] = (pres.groupby("planta")["kwh_por_eq_presupuesto"].transform(lambda s: s.ne(s.shift()).cumsum()))
    metas = (pres.groupby(["planta", "grupo"]).agg(kwh_por_eq_meta=("kwh_por_eq_presupuesto", "first"), vigente_desde=("mes", "min"),
                                                   vigente_hasta=("mes", "max"), meses=("mes", "size")).reset_index().drop(columns="grupo"))
    metas["fuente"] = "Base de datos.xlsx (presupuesto de Clarios)"
    metas.round(3).to_csv(CLEAN / "metas_clarios.csv", index=False)

    print("Correcciones de fecha / saltos de secuencia:", avisos_tot if avisos_tot else "ninguno")
    print("\nPeriodo por planta:")
    print(base.groupby("planta")["mes"].agg(["min", "max", "count"]).to_string())
    print("\nTarifa del kWh de Clarios (COP/kWh) por mes, desde que existe:")
    print(tarifa.round(2).to_string(index=False))
    print(f"\nMeta de kWh por equivalente (presupuesto de Clarios):\n{metas.round(2).to_string(index=False)}")
    print(f"\nPlantas con tarifa distinta el mismo mes: {int((tar['max'] - tar['min'] > 0.01).sum())} meses")

    # indicador de Clarios frente a producción: el efecto de la producción baja
    print("\nEl indicador kWh por equivalente cuando baja la producción (año fiscal 2026, Ensamble):")
    e = base[(base["planta"] == "Ensamble") & (base["mes"] >= pd.Timestamp("2025-10-01").date())][["mes", "kwh", "produccion_equivalente", "kwh_por_eq"]]
    e = e.assign(var_kwh_pct=e["kwh"].pct_change().mul(100).round(0), var_prod_pct=e["produccion_equivalente"].pct_change().mul(100).round(0),
                 var_indicador_pct=e["kwh_por_eq"].pct_change().mul(100).round(0))
    print(e.round(2).to_string(index=False))

    # ¿Qué mide la "producción equivalente" de RC? Se compara con la refinación del ERP (toneladas)
    pt = pd.read_csv(CLEAN / "produccion_turno.csv", parse_dates=["fecha_turno"])
    ref = pt[pt["linea_erp"].isin(["RCREFI01", "RCREFI02", "RCREFI03"])].copy()
    ref["mes"] = ref["fecha_turno"].dt.to_period("M").dt.to_timestamp().dt.date
    t_ref = (ref.groupby("mes")["cantidad"].sum() / 1000).rename("refinacion_toneladas")
    rc = base[base["planta"] == "RC"].set_index("mes")[["produccion_equivalente"]].join(t_ref, how="inner")
    rc["ratio"] = (rc["refinacion_toneladas"] / rc["produccion_equivalente"]).round(2)
    print("\nRC: producción equivalente de Clarios frente a toneladas refinadas del ERP (RCREFI01 a 03):")
    print(rc.round(1).to_string())
    print("Correlación:", round(rc["produccion_equivalente"].corr(rc["refinacion_toneladas"]), 3))


if __name__ == "__main__":
    main()
