"""Paso 3 (Datos): tablas para modelar (RC y F&A): calendario de operación y dataset_modelo por turno, día y semana.

Requiere haber corrido antes 01_energia_scada.py, 02_produccion_erp.py y 05_energia_fa.py.
Uso (desde la raíz del repositorio):  python src/datos/03_dataset_modelo.py

Salidas en data/clean: calendario_operacion, dataset_modelo (turno), dataset_modelo_dia, dataset_modelo_semana

Todo lo que es una decisión (turnos, cobertura mínima, procesos asociados, regla de `operando`, calendario de festivos)
sale de config/config.yaml. Decisiones (ver documentacion/04_supuestos_y_limitaciones.md):
  - La producción de RC se reporta por lotes (60 a 80% de los turnos no tienen transacciones), por eso la relación
    energía-producción es débil por turno y fuerte por semana. Se entregan los tres niveles.
  - `kwh` es el consumo reescalado a cobertura completa (kwh_observado / cobertura) cuando la cobertura es suficiente.
    Si la cobertura es menor a calidad.cobertura_minima, `kwh` queda vacío.
  - `operando` se infiere de la energía (no hay calendario real de Clarios): kwh del turno mayor al mayor entre
    operando_multiplo_p5 x p5 y operando_fraccion_p95 x p95 del proceso.
  - El periodo de las tablas es el de la producción del ERP (primera a última fecha_turno de produccion_turno).
"""
import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, mapa_procesos  # noqa: E402
from src.comun.turnos import horas_por_turno  # noqa: E402

CLEAN = RAIZ / "data" / "clean"
CFG = cargar_config()
MIN_COB = CFG["calidad"]["cobertura_minima"]
MOD = CFG["modelado"]
HORAS_TURNO = horas_por_turno(CFG)
N_TURNOS = len(HORAS_TURNO)


def main():
    mapa = [p for p in mapa_procesos(CFG) if p["modelar"] and p["medidores_scada"]]
    planta_de = {p["proceso_modelo"]: p["planta"] for p in mapa}
    unidad_de = {p["proceso_modelo"]: p["unidad_produccion"] for p in mapa}
    medidor_a_proceso = {m: p["proceso_modelo"] for p in mapa for m in p["medidores_scada"]}
    esperados = {p["proceso_modelo"]: len(p["medidores_scada"]) for p in mapa}

    pt = pd.read_csv(CLEAN / "produccion_turno.csv", parse_dates=["fecha_turno"])
    INI, FIN = pt["fecha_turno"].min(), pt["fecha_turno"].max()
    festivos = holidays.country_holidays(CFG["calendario"]["pais_festivos"], years=range(INI.year, FIN.year + 1))

    et = pd.read_csv(CLEAN / "energia_turno.csv", parse_dates=["fecha_turno"])
    et["proceso_modelo"] = et["medidor"].map(medidor_a_proceso)
    et = et.dropna(subset=["proceso_modelo"])
    # una hora de un proceso cuenta solo si TODOS sus medidores son válidos
    g = et.groupby(["fecha_turno", "turno", "proceso_modelo"])
    E = g.agg(kwh_observado=("kwh", "sum"), horas_validas=("horas_validas", "min"), n_medidores=("medidor", "nunique")).reset_index()
    E["completo"] = E["n_medidores"] == E["proceso_modelo"].map(esperados)
    E.loc[~E["completo"], "horas_validas"] = 0
    E["horas_turno"] = E["turno"].map(HORAS_TURNO)
    E["cobertura"] = (E["horas_validas"] / E["horas_turno"]).round(3)
    E = E[(E["fecha_turno"] >= INI) & (E["fecha_turno"] <= FIN)]

    # producción neta por proceso y turno
    pr = pt[pt["planta"].isin(["RC", "F&A"]) & pt["proceso_modelo"].notna() & pt["proceso_modelo"].ne("")]
    P = (pr.groupby(["fecha_turno", "turno", "proceso_modelo"]).agg(produccion=("cantidad", "sum"), n_transacciones=("n_transacciones", "sum"))
         .reset_index())
    extra = []
    for hijo, padre in MOD["procesos_asociados"].items():
        x = P[P["proceso_modelo"] == padre].copy()
        x["proceso_modelo"] = hijo
        extra.append(x)
    P = pd.concat([P] + extra, ignore_index=True)

    D = E.merge(P, on=["fecha_turno", "turno", "proceso_modelo"], how="left")
    D[["produccion", "n_transacciones"]] = D[["produccion", "n_transacciones"]].fillna(0)
    D["planta"] = D["proceso_modelo"].map(planta_de)
    D["unidad"] = D["proceso_modelo"].map(unidad_de)
    D["dia_semana"] = D["fecha_turno"].dt.dayofweek
    D["es_fin_semana"] = (D["dia_semana"] >= 5).astype(int)
    D["es_festivo"] = D["fecha_turno"].dt.date.map(lambda d: int(d in festivos))
    D["kwh"] = np.where(D["cobertura"] >= MIN_COB, D["kwh_observado"] / D["cobertura"].replace(0, np.nan), np.nan)

    # operando (inferido de la energía)
    ref = D[D["cobertura"] >= 1].groupby("proceso_modelo")["kwh"]
    umbral = pd.concat([MOD["operando_multiplo_p5"] * ref.quantile(0.05), MOD["operando_fraccion_p95"] * ref.quantile(0.95)], axis=1).max(axis=1)
    D["umbral_operando"] = D["proceso_modelo"].map(umbral)
    D["operando"] = np.where(D["kwh"].isna(), np.nan, (D["kwh"] > D["umbral_operando"]).astype(float))
    D["calidad_ok"] = (D["cobertura"] >= MIN_COB).astype(int)

    cal = D[["fecha_turno", "turno", "planta", "proceso_modelo", "operando"]].copy()
    cal["operando"] = cal["operando"].astype("Int64")
    cal["fuente"] = "inferido"
    cal["fecha_turno"] = cal["fecha_turno"].dt.date
    cal.sort_values(["fecha_turno", "turno", "proceso_modelo"]).to_csv(CLEAN / "calendario_operacion.csv", index=False)

    cols = ["fecha_turno", "turno", "planta", "proceso_modelo", "kwh", "kwh_observado", "produccion", "unidad", "n_transacciones",
            "dia_semana", "es_fin_semana", "es_festivo", "operando", "cobertura", "calidad_ok"]
    out = D[cols].copy()
    out["fecha_turno"] = out["fecha_turno"].dt.date
    out[["kwh", "kwh_observado", "produccion"]] = out[["kwh", "kwh_observado", "produccion"]].round(3)
    out["operando"] = out["operando"].astype("Int64")
    out["n_transacciones"] = out["n_transacciones"].astype(int)
    out.sort_values(["fecha_turno", "turno", "proceso_modelo"]).to_csv(CLEAN / "dataset_modelo.csv", index=False)

    # nivel día y semana (solo intervalos completos: todos los turnos del día o de la semana)
    def agregar(df, clave, nombre_fecha, turnos_por_unidad):
        a = (df.groupby([clave, "proceso_modelo"])
             .agg(kwh_observado=("kwh_observado", "sum"), horas_validas=("horas_validas", "sum"), horas_turno=("horas_turno", "sum"),
                  produccion=("produccion", "sum"), n_transacciones=("n_transacciones", "sum"), turnos_operando=("operando", "sum"),
                  turnos_con_dato=("operando", "count"), turnos_festivos=("es_festivo", "sum"), n_turnos=("turno", "size")).reset_index())
        a["cobertura"] = (a["horas_validas"] / a["horas_turno"]).round(3)
        a["kwh"] = np.where(a["cobertura"] >= MIN_COB, a["kwh_observado"] / a["cobertura"].replace(0, np.nan), np.nan)
        a = a[a["n_turnos"] == turnos_por_unidad]
        a = a.rename(columns={clave: nombre_fecha})
        a["planta"] = a["proceso_modelo"].map(planta_de)
        a["unidad"] = a["proceso_modelo"].map(unidad_de)
        a["pct_turnos_operando"] = (a["turnos_operando"] / a["turnos_con_dato"].replace(0, np.nan)).round(3)
        a["calidad_ok"] = (a["cobertura"] >= MIN_COB).astype(int)
        a["n_transacciones"] = a["n_transacciones"].astype(int)
        return a

    dia = agregar(D.assign(dia=D["fecha_turno"]), "dia", "fecha", N_TURNOS)
    dia["dia_semana"] = dia["fecha"].dt.dayofweek
    dia["es_fin_semana"] = (dia["dia_semana"] >= 5).astype(int)
    dia["es_festivo"] = (dia["turnos_festivos"] > 0).astype(int)
    cols_d = ["fecha", "planta", "proceso_modelo", "kwh", "kwh_observado", "produccion", "unidad", "n_transacciones", "dia_semana",
              "es_fin_semana", "es_festivo", "pct_turnos_operando", "cobertura", "calidad_ok"]
    dia["fecha"] = dia["fecha"].dt.date
    dia[cols_d].round(3).sort_values(["fecha", "proceso_modelo"]).to_csv(CLEAN / "dataset_modelo_dia.csv", index=False)

    D["semana"] = D["fecha_turno"] - pd.to_timedelta(D["fecha_turno"].dt.dayofweek, unit="D")
    Dw = D[(D["semana"] >= INI) & (D["semana"] + pd.Timedelta(days=6) <= FIN)]
    sem = agregar(Dw, "semana", "semana_inicio", 7 * N_TURNOS)
    sem["dias_festivos"] = (sem["turnos_festivos"] / N_TURNOS).round().astype(int)
    sem["semana_inicio"] = sem["semana_inicio"].dt.date
    cols_s = ["semana_inicio", "planta", "proceso_modelo", "kwh", "kwh_observado", "produccion", "unidad", "n_transacciones",
              "dias_festivos", "pct_turnos_operando", "cobertura", "calidad_ok"]
    sem[cols_s].round(3).sort_values(["semana_inicio", "proceso_modelo"]).to_csv(CLEAN / "dataset_modelo_semana.csv", index=False)

    print("Umbral de 'operando' por proceso (kWh por turno):\n", umbral.round(1).to_string())
    print(f"\ndataset_modelo (turno): {len(out):,} filas | calidad_ok={out['calidad_ok'].mean():.1%} | operando={out['operando'].mean():.1%}")
    print(f"dataset_modelo_dia: {len(dia):,} filas | dataset_modelo_semana: {len(sem):,} filas")
    print("\nFilas por proceso (turno / día / semana):")
    print(pd.DataFrame({"turno": out.groupby("proceso_modelo").size(), "dia": dia.groupby("proceso_modelo").size(),
                        "semana": sem.groupby("proceso_modelo").size()}).to_string())
    print("\nCorrelación kWh ~ producción (filas con calidad_ok), por nivel:")
    res = {}
    for nombre, t in [("turno", out), ("día", dia), ("semana", sem)]:
        t = t[t["calidad_ok"] == 1]
        res[nombre] = t.groupby("proceso_modelo").apply(lambda g: round(g[["kwh", "produccion"]].corr().iloc[0, 1], 2), include_groups=False)
    print(pd.DataFrame(res).to_string())


if __name__ == "__main__":
    main()
