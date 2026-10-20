"""Paso 6 (Datos): consumo diario de gas de refinación (RC) desde el SCADA.

El SCADA entrega un acumulado de gas (m3) que se reinicia cada vez que llega a unos 14,000 a 17,000. Aquí se
convierte en consumo por día (de medianoche a medianoche) con marcas de calidad:
  ok        consumo medido entre dos lecturas válidas
  estimado  el día cae dentro de un hueco de lecturas de más de gas.hueco_estimado_horas horas y el consumo se repartió de forma uniforme
  reinicio  el acumulado se reinició durante el día: se informa solo lo contado después del reinicio (límite inferior)

Uso (desde la raíz del repositorio):  python src/datos/06_gas.py
Salidas en data/clean: gas_dia, dataset_modelo_gas_dia
"""
import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config  # noqa: E402

RAW = RAIZ / "data" / "raw"
CLEAN = RAIZ / "data" / "clean"
CFG = cargar_config()
HUECO_ESTIMADO_H = CFG["gas"]["hueco_estimado_horas"]
TOL_S = float(CFG["gas"]["tolerancia_medianoche_s"])  # las lecturas diarias caen unos segundos antes o después de la medianoche


def gas_diario(t, v):
    s = pd.DataFrame({"t": t, "v": v}).dropna().sort_values("t").drop_duplicates("t", keep="last").reset_index(drop=True)
    sec = (s["t"] - s["t"].min().normalize()).dt.total_seconds().to_numpy()
    val = s["v"].to_numpy(float)
    d = np.diff(val)
    dt_h = np.diff(sec) / 3600
    reinicio = d < 0
    aporte = np.where(reinicio, val[1:], d)  # tras un reinicio solo se conoce lo contado después
    cv = np.concatenate([[0.0], np.cumsum(aporte)])
    origen = s["t"].min().normalize()
    primer, ultimo = int(np.ceil((sec[0] - TOL_S) / 86400)), int(np.floor((sec[-1] + TOL_S) / 86400))
    marcas = np.arange(primer, ultimo + 1) * 86400.0
    m3 = np.diff(np.interp(marcas, sec, cv))
    n = len(m3)
    calidad = np.array(["ok"] * n, dtype=object)
    for i in np.flatnonzero(dt_h > HUECO_ESTIMADO_H):
        lo, hi = max(int(np.floor((sec[i] + TOL_S) / 86400)) - primer, 0), min(int(np.ceil((sec[i + 1] - TOL_S) / 86400)) - 1 - primer, n - 1)
        calidad[lo:hi + 1] = "estimado"
    for i in np.flatnonzero(reinicio):
        lo, hi = max(int(np.floor((sec[i] + TOL_S) / 86400)) - primer, 0), min(int(np.ceil((sec[i + 1] - TOL_S) / 86400)) - 1 - primer, n - 1)
        calidad[lo:hi + 1] = "reinicio"
    fechas = origen + pd.to_timedelta(marcas[:-1], unit="s")
    return pd.DataFrame({"fecha": fechas, "m3": m3, "calidad": calidad}), int(reinicio.sum())


def main():
    raw = pd.read_excel(RAW / "SCADA-Base de datos GAS RC.xlsx", engine="calamine")
    raw.columns = ["t", "acumulado_m3", "consumo_diario_scada"]
    raw["t"] = pd.to_datetime(raw["t"])
    print(f"Lecturas: {len(raw)} del {raw['t'].min()} al {raw['t'].max()}")
    g, n_reinicios = gas_diario(raw["t"], raw["acumulado_m3"])
    print(f"Reinicios del acumulado detectados: {n_reinicios}")
    g["m3"] = g["m3"].round(1)
    out = g.copy()
    out["fecha"] = out["fecha"].dt.date
    out.to_csv(CLEAN / "gas_dia.csv", index=False)

    # comparación con la columna "Consumo_Diario" que trae el SCADA
    cmp = raw.copy()
    cmp["fecha"] = (cmp["t"] - pd.Timedelta(minutes=5)).dt.normalize()
    cmp = cmp[(cmp["t"].dt.hour == 23) | (cmp["t"].dt.hour == 0)].drop_duplicates("fecha", keep="last")
    cmp = cmp.merge(g, on="fecha")
    ok = cmp[cmp["calidad"] == "ok"]
    print(f"\nDías ok: {int((g['calidad'] == 'ok').sum())}, estimados: {int((g['calidad'] == 'estimado').sum())}, con reinicio: {int((g['calidad'] == 'reinicio').sum())}")
    print(f"Comparación con 'Consumo_Diario' del SCADA en {len(ok)} días ok: diferencia absoluta mediana {np.median(np.abs(ok['m3'] - ok['consumo_diario_scada'])):.1f} m3")

    g["mes"] = g["fecha"].dt.to_period("M")
    mens = g.groupby("mes").agg(m3=("m3", "sum"), dias=("m3", "size"), dias_reinicio=("calidad", lambda s: int((s == "reinicio").sum())),
                                dias_estimados=("calidad", lambda s: int((s == "estimado").sum())))
    print("\nConsumo mensual de gas del SCADA (m3):\n", mens.round(0).to_string())
    b = pd.read_excel(RAW / "Base de datos.xlsx", sheet_name="RC GAS", header=1, engine="calamine")
    b.columns = [str(c).strip() for c in b.columns]
    print("\nBase de Clarios (RC GAS), últimos 6 meses con dato (m3 por mes):")
    print(b[b["Proceso"].astype(str).str.strip() == "RC"].tail(6)[["Año", "Mes", "(m3)"]].to_string(index=False))

    # dataset para modelar: gas diario contra producción diaria de RC
    dd = pd.read_csv(CLEAN / "dataset_modelo_dia.csv", parse_dates=["fecha"])
    prod = dd[dd["proceso_modelo"].isin(["horno", "refinacion"])].pivot_table(index="fecha", columns="proceso_modelo", values="produccion")
    prod.columns = [f"produccion_{c}_kg" for c in prod.columns]
    m = g.drop(columns="mes").merge(prod.reset_index(), on="fecha", how="left")
    m["dia_semana"] = m["fecha"].dt.dayofweek
    m["es_fin_semana"] = (m["dia_semana"] >= 5).astype(int)
    festivos = holidays.country_holidays(CFG["calendario"]["pais_festivos"], years=sorted(set(m["fecha"].dt.year)))
    m["es_festivo"] = m["fecha"].dt.date.map(lambda d: int(d in festivos))
    m["calidad_ok"] = (m["calidad"] == "ok").astype(int)
    m["fecha"] = m["fecha"].dt.date
    m.round(1).to_csv(CLEAN / "dataset_modelo_gas_dia.csv", index=False)
    mm = m[m["calidad_ok"] == 1]
    print(f"\ndataset_modelo_gas_dia: {len(m)} días ({len(mm)} con calidad ok). Correlación m3 vs producción diaria (días ok):")
    print(mm[["m3", "produccion_horno_kg", "produccion_refinacion_kg"]].corr().round(2).iloc[0].to_string())
    print(f"m3 por día: media {mm['m3'].mean():.0f}, mediana {mm['m3'].median():.0f}, p10 {mm['m3'].quantile(.1):.0f}, p90 {mm['m3'].quantile(.9):.0f}")


if __name__ == "__main__":
    main()
