"""Paso 5 (Datos): energía horaria de F&A (3 rectificadores de formación) desde el SCADA.

Mismo procedimiento que RC (ver energia_comun.py). Los datos van del 2 de julio al 1 de octubre de 2026.
Las tablas energia_hora y energia_turno se comparten con RC: aquí solo se reemplazan las filas de F&A.

Uso (desde la raíz del repositorio):  python src/datos/05_energia_fa.py
Salidas en data/clean: energia_hora, energia_turno, calidad_energia_fa, congelamientos_energia_fa, rachas_constantes_energia,
cobertura_energia_mensual, validacion_energia_fa_mensual

Unidad: no está confirmada. Se asume Wh, igual que en RC. Gabriel informó que los rectificadores vienen "en GW";
la magnitud de los acumulados (unos 2e10) solo es coherente con Wh. Por confirmar con Clarios.
"""
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, medidores_proceso  # noqa: E402
from src.datos.energia_comun import (actualizar_tabla, cargar_base_mensual, procesar_planta, tabla_cobertura_mensual,  # noqa: E402
                                     tablas_energia)

RAW = RAIZ / "data" / "raw"
CLEAN = RAIZ / "data" / "clean"
CFG = cargar_config()
MEDIDORES_PROCESO = medidores_proceso("F&A", CFG)


def main():
    cal, k = CFG["calidad"], CFG["unidades"]["contador_energia_a_kwh"]
    df = pd.read_excel(RAW / "SCADA-Base de datos F&A.xlsx", engine="calamine")
    df = df.rename(columns={"t_stamp": "t"})
    df.columns = ["t"] + [c.strip().upper().replace(" ", "_") for c in df.columns[1:]]
    df["t"] = pd.to_datetime(df["t"])

    hora, resumen, cong, n_cero, rachas = procesar_planta(df, "F&A", MEDIDORES_PROCESO, cal, k, CFG["rachas"], CFG["calendario"]["pais_festivos"])
    print(f"Lecturas: {len(df):,} del {df['t'].min()} al {df['t'].max()}. Filas con todo en 0 (se descartan): {n_cero}")
    if len(cong):
        cong.to_csv(CLEAN / "congelamientos_energia_fa.csv", index=False)
        print("\nCongelamientos detectados:\n", cong.to_string(index=False))
    else:
        print("\nNo se detectaron congelamientos del SCADA en F&A.")

    actualizar_tabla("rachas_constantes_energia", rachas, "F&A", ["inicio", "medidor"])
    actualizar_tabla("cobertura_energia_mensual", tabla_cobertura_mensual(hora), "F&A", ["mes", "medidor"])
    print(f"\nRachas sin cambio por medidor (>= {cal['min_intervalos_congelado']} intervalos): {len(rachas)}")
    print(rachas.groupby(["clasificacion", "confianza", "tratamiento"]).agg(rachas=("horas", "size"), horas=("horas", "sum")).to_string())

    eh, et = tablas_energia(hora)
    actualizar_tabla("energia_hora", eh, "F&A", ["hora_inicio", "medidor"])
    actualizar_tabla("energia_turno", et, "F&A", ["fecha_turno", "turno", "planta", "medidor"])
    resumen.to_csv(CLEAN / "calidad_energia_fa.csv", index=False)

    hora["mes"] = hora["hora_inicio"].dt.to_period("M")
    mens = hora.groupby("mes").agg(kwh_scada_3_rectificadores=("kwh_t", "sum"), horas_validas=("valida_total", "sum"),
                                   horas_total=("valida_total", "size"))
    mens["cobertura"] = (mens["horas_validas"] / mens["horas_total"]).round(3)
    base = cargar_base_mensual("F&A", "F&A")
    mens = mens.join(base)
    mens.round(3).to_csv(CLEAN / "validacion_energia_fa_mensual.csv", index_label="mes")

    print("\nCalidad por medidor (horas):")
    print(resumen[["medidor", "reinicios", "saltos", "huecos_largos", "congelamientos_repartidos", "horas_total",
                   "pct_horas_ok_o_interpoladas"]].to_string(index=False))
    print("\nConsumo mensual SCADA (si el contador está en Wh) y últimos meses de la base mensual de Clarios (kWh):")
    print(mens[["kwh_scada_3_rectificadores", "cobertura"]].round(0).to_string())
    print(base.tail(9).round(0).to_string())
    print("\nPromedio base Clarios, últimos 6 meses con dato:", round(base.tail(6).mean()),
          "| promedio SCADA jul-sep:", round(mens["kwh_scada_3_rectificadores"].iloc[1:-1].mean()))
    q = hora[hora["valida"]].groupby("medidor")["kwh"].describe()[["mean", "min", "50%", "max"]].round(0)
    print("\nkWh por hora por rectificador (horas válidas):\n", q.to_string())
    print(f"\nFilas F&A: energia_hora={len(eh):,}  energia_turno={len(et):,}")


if __name__ == "__main__":
    main()
