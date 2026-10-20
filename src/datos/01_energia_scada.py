"""Paso 1 (Datos): energía horaria de RC desde el SCADA.

Convierte contadores acumulados en kWh por hora y por turno, con marcas de calidad (ver energia_comun.py),
y valida contra la base mensual de Clarios. Los medidores, los umbrales y los turnos salen de config/config.yaml.

Uso (desde la raíz del repositorio):  python src/datos/01_energia_scada.py

Salidas en data/clean (las tablas energia_hora y energia_turno se comparten con F&A: aquí solo se reemplazan
las filas de RC):
  energia_hora, energia_turno, mapa_procesos, calidad_energia_rc, congelamientos_energia_rc,
  rachas_constantes_energia (rachas sin cambio por medidor, clasificadas con confianza), cobertura_energia_mensual,
  validacion_energia_rc_mensual
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, medidores_proceso, tabla_mapa_procesos  # noqa: E402
from src.datos.energia_comun import (actualizar_tabla, cargar_base_mensual, procesar_planta, tabla_cobertura_mensual,  # noqa: E402
                                     tablas_energia)

RAW = RAIZ / "data" / "raw"
CLEAN = RAIZ / "data" / "clean"
CFG = cargar_config()
MEDIDORES_PROCESO = medidores_proceso("RC", CFG)


def main():
    cal, k = CFG["calidad"], CFG["unidades"]["contador_energia_a_kwh"]
    CLEAN.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(RAW / "SCADA-Base de datos Energia RC.xlsx", engine="calamine")
    df = df.rename(columns={"t_stamp": "t"})
    df.columns = ["t"] + [c.strip().upper().replace(" ", "_") for c in df.columns[1:]]
    df["t"] = pd.to_datetime(df["t"])

    hora, resumen, cong, n_cero, rachas = procesar_planta(df, "RC", MEDIDORES_PROCESO, cal, k, CFG["rachas"], CFG["calendario"]["pais_festivos"])
    print(f"Lecturas: {len(df):,}. Filas con todos los medidores en 0 (se descartan): {n_cero}")
    if len(cong):
        cong.to_csv(CLEAN / "congelamientos_energia_rc.csv", index=False)
        print(f"\nCongelamientos detectados (todos los medidores de proceso sin cambio >= {cal['min_intervalos_congelado']} horas): {len(cong)}")
        print(cong.to_string(index=False))

    actualizar_tabla("rachas_constantes_energia", rachas, "RC", ["inicio", "medidor"])
    actualizar_tabla("cobertura_energia_mensual", tabla_cobertura_mensual(hora), "RC", ["mes", "medidor"])
    print(f"\nRachas sin cambio por medidor (>= {cal['min_intervalos_congelado']} intervalos): {len(rachas)}")
    print(rachas.groupby(["clasificacion", "confianza", "tratamiento"]).agg(rachas=("horas", "size"), horas=("horas", "sum")).to_string())

    eh, et = tablas_energia(hora)
    actualizar_tabla("energia_hora", eh, "RC", ["hora_inicio", "medidor"])
    actualizar_tabla("energia_turno", et, "RC", ["fecha_turno", "turno", "planta", "medidor"])
    resumen.to_csv(CLEAN / "calidad_energia_rc.csv", index=False)

    # validación mensual contra la base de Clarios (los totales incluyen horas "estimadas" por congelamiento)
    hora["mes"] = hora["hora_inicio"].dt.to_period("M")
    proc = hora[hora["medidor"].isin(MEDIDORES_PROCESO)]
    pm = (proc.groupby(["mes", "medidor"]).agg(kwh=("kwh_t", "sum"), validas=("valida_total", "sum"), total=("valida_total", "size"))
          .reset_index())
    pm["kwh_est"] = pm["kwh"] * pm["total"] / pm["validas"].replace(0, np.nan)
    mens = pm.groupby("mes").agg(kwh_scada_7_procesos=("kwh", "sum"), kwh_estimado_por_cobertura=("kwh_est", "sum"),
                                 horas_validas=("validas", "sum"), horas_total=("total", "sum"))
    mens["cobertura"] = (mens["horas_validas"] / mens["horas_total"]).round(3)
    horas_estim = proc[proc["calidad"] == "estimado"].groupby("mes").size()
    mens["horas_estimadas_por_congelamiento"] = horas_estim.reindex(mens.index).fillna(0).astype(int)
    for extra in ["EMCALI", "EDIF_ADMON"]:
        e = hora[hora["medidor"] == extra].groupby("mes")["kwh_t"].sum()
        mens[f"kwh_{extra.lower()}_si_contador_en_wh"] = e
    mens = mens.join(cargar_base_mensual("RC Energia", "RC"))
    mens["ratio_scada_vs_base"] = (mens["kwh_scada_7_procesos"] / mens["kwh_base_clarios"]).round(3)
    mens["ratio_estimado_vs_base"] = (mens["kwh_estimado_por_cobertura"] / mens["kwh_base_clarios"]).round(3)
    horas_posibles = len(MEDIDORES_PROCESO) * 24 * pd.Series(mens.index.days_in_month, index=mens.index)
    mens["mes_completo"] = mens["horas_total"] >= horas_posibles * cal["cobertura_mes_completo"]
    mens.round(3).to_csv(CLEAN / "validacion_energia_rc_mensual.csv", index_label="mes")

    tabla_mapa_procesos(CFG).to_csv(CLEAN / "mapa_procesos.csv", index=False)

    print("\nCalidad por medidor (horas):")
    cols = ["medidor", "reinicios", "saltos", "huecos_largos", "congelamientos_repartidos", "horas_total",
            "horas_estimado", "pct_horas_ok_o_interpoladas"]
    print(resumen[cols].to_string(index=False))
    print("\nValidación mensual (7 medidores de proceso vs base de Clarios), meses completos:")
    v = mens[mens["mes_completo"]][["kwh_scada_7_procesos", "kwh_base_clarios", "ratio_scada_vs_base", "cobertura", "horas_estimadas_por_congelamiento"]]
    print(v.round(2).to_string())
    print(f"\nFilas RC: energia_hora={len(eh):,}  energia_turno={len(et):,}")


if __name__ == "__main__":
    main()
